<script lang="ts">
	import { getContext, onDestroy, onMount, tick } from 'svelte';
	import dayjs from 'dayjs';
	import utc from 'dayjs/plugin/utc';
	import { Chart, registerables } from 'chart.js';
	import * as XLSX from 'xlsx';
	import jsPDF from 'jspdf';
	import autoTable from 'jspdf-autotable';
	import { toast } from 'svelte-sonner';

	import {
		getAnalyticsSummary,
		getLineChartFilterOptions,
		getModelUsage,
		getUsageOverTime,
		getUserActivity,
		getUserActivityHeatmap,
		type AnalyticsSummary,
		type HeatmapDayRow,
		type ModelUsageRow,
		type UsageOverTimeRow,
		type UserActivityRow
	} from '$lib/apis/analytics';

	import Download from '$lib/components/icons/Download.svelte';
	import ArrowsPointingOut from '$lib/components/icons/ArrowsPointingOut.svelte';

	dayjs.extend(utc);

	const i18n = getContext('i18n');

	const PALETTE = [
		'#3B4BC8',
		'#2EC4B6',
		'#5E81F4',
		'#F4A261',
		'#E76F51',
		'#A8DADC',
		'#457B9D',
		'#1D3557',
		'#999999'
	];

	const PIE_TOP_N = 8;

	type PieSliceRow = {
		label: string;
		messages: number;
		tokens: number;
		sharePercent: number;
	};

	/** Pie shows top N models by message volume; remaining rows merge into "Others". */
	function computePieSlices(rows: ModelUsageRow[], othersLabel: string): PieSliceRow[] {
		if (rows.length === 0) return [];
		const totalMsgs = rows.reduce((s, r) => s + r.messages, 0);
		const sorted = [...rows].sort((a, b) => b.messages - a.messages);
		const pct = (m: number) => (totalMsgs > 0 ? (m / totalMsgs) * 100 : 0);
		if (sorted.length <= PIE_TOP_N) {
			return sorted.map((r) => ({
				label: r.model,
				messages: r.messages,
				tokens: r.tokens,
				sharePercent: pct(r.messages)
			}));
		}
		const top = sorted.slice(0, PIE_TOP_N);
		const rest = sorted.slice(PIE_TOP_N);
		const othersMessages = rest.reduce((s, r) => s + r.messages, 0);
		const othersTokens = rest.reduce((s, r) => s + r.tokens, 0);
		return [
			...top.map((r) => ({
				label: r.model,
				messages: r.messages,
				tokens: r.tokens,
				sharePercent: pct(r.messages)
			})),
			{
				label: othersLabel,
				messages: othersMessages,
				tokens: othersTokens,
				sharePercent: pct(othersMessages)
			}
		];
	}

	let pieSlices: PieSliceRow[] = [];

	let summary: AnalyticsSummary | null = null;
	let summaryLoading = true;
	let summaryError: string | null = null;

	let modelUsageRows: ModelUsageRow[] = [];
	let userActivityRows: UserActivityRow[] = [];
	let tablesLoading = true;
	let tablesError: string | null = null;

	/** Line chart filters only: derived from chats with real usage (see API). */
	let lineChartUsers: { id: string; name: string }[] = [];
	let lineChartModels: { id: string; name: string }[] = [];

	let selectedUserId = '';
	let selectedModelId = '';
	let metric: 'messages' | 'tokens' = 'messages';
	let timePreset: '7' | '20' | '30' | 'all' | 'custom' = '7';
	let customStart = '';
	let customEnd = '';
	let showCalendar = false;
	let lineExportOpen = false;
	let tableExportOpen = false;
	let tableExporting = false;

	let lineSmooth = true;
	let lineLoading = false;
	let lineError: string | null = null;
	let lineRaw: UsageOverTimeRow[] = [];

	let pieCanvas: HTMLCanvasElement | null = null;
	let lineCanvas: HTMLCanvasElement | null = null;
	let pieChart: Chart | null = null;
	let lineChart: Chart | null = null;

	let modelModalOpen = false;
	let userModalOpen = false;

	type SortDir = 'asc' | 'desc';
	let modelSort: { key: keyof ModelUsageRow; dir: SortDir } = {
		key: 'messages',
		dir: 'desc'
	};
	let userSort: { key: keyof UserActivityRow; dir: SortDir } = {
		key: 'messages',
		dir: 'desc'
	};

	const HEATMAP_CY = new Date().getFullYear();
	const MONTH_LABELS = [
		'Jan',
		'Feb',
		'Mar',
		'Apr',
		'May',
		'Jun',
		'Jul',
		'Aug',
		'Sep',
		'Oct',
		'Nov',
		'Dec'
	];
	const HEAT_COLORS = ['#ebebeb', '#c6e9e7', '#7ececb', '#4db6ac', '#e85d04'];

	let heatmapRows: HeatmapDayRow[] = [];
	let heatmapYear = HEATMAP_CY;
	let heatmapSelectStr = String(HEATMAP_CY);
	let heatmapLoading = false;
	let heatmapError: string | null = null;
	let showHeatmapYearPicker = false;
	let heatTooltip: {
		x: number;
		y: number;
		dateLabel: string;
		messages: number;
		tokens: number;
		empty: boolean;
	} | null = null;

	$: presetHeatmapYears = [HEATMAP_CY, HEATMAP_CY - 1, HEATMAP_CY - 2, HEATMAP_CY - 3];
	$: heatmapYearOptions = (() => {
		const s = new Set([...presetHeatmapYears, heatmapYear]);
		return [...s].sort((a, b) => b - a);
	})();
	$: heatmapByDate = new Map(heatmapRows.map((r) => [r.date, { messages: r.messages, tokens: r.tokens }]));

	function fmtUsd(n: number) {
		return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function formatAxisDate(iso: string) {
		const [y, m, d] = iso.split('-').map(Number);
		return `${m}/${d}`;
	}

	function dateRange(): { start: string; end: string } {
		const end = dayjs.utc().format('YYYY-MM-DD');
		if (timePreset === 'custom') {
			if (customStart && customEnd) {
				return { start: customStart, end: customEnd };
			}
			const start = dayjs.utc().subtract(6, 'day').format('YYYY-MM-DD');
			return { start, end };
		}
		if (timePreset === 'all') {
			return { start: '2020-01-01', end };
		}
		const daysBack =
			timePreset === '20' ? 19 : timePreset === '30' ? 29 : 6;
		const start = dayjs.utc().subtract(daysBack, 'day').format('YYYY-MM-DD');
		return { start, end };
	}

	function eachDayInclusive(start: string, end: string): string[] {
		const out: string[] = [];
		let d = dayjs.utc(start);
		const e = dayjs.utc(end);
		while (d.isBefore(e) || d.isSame(e, 'day')) {
			out.push(d.format('YYYY-MM-DD'));
			d = d.add(1, 'day');
		}
		return out;
	}

	function colorForModel(modelId: string): string {
		const idx = modelUsageRows.findIndex((r) => r.model_id === modelId);
		if (idx >= 0) return PALETTE[idx % PALETTE.length];
		return PALETTE[8];
	}

	function mondayIndex(d: Date): number {
		return (d.getDay() + 6) % 7;
	}

	function heatLevel(messages: number): number {
		if (messages <= 0) return 0;
		if (messages <= 2) return 1;
		if (messages <= 5) return 2;
		if (messages <= 10) return 3;
		return 4;
	}

	function heatBg(messages: number): string {
		return HEAT_COLORS[heatLevel(messages)];
	}

	function buildMonthColumns(
		year: number,
		month: number,
		byDate: Map<string, { messages: number; tokens: number }>
	) {
		const first = new Date(year, month - 1, 1);
		const last = new Date(year, month, 0);
		const startMonday = new Date(first);
		startMonday.setDate(first.getDate() - mondayIndex(first));
		const endSunday = new Date(last);
		endSunday.setDate(last.getDate() + (6 - mondayIndex(last)));

		const columns: {
			cells: { iso: string | null; messages: number; tokens: number; show: boolean }[];
		}[] = [];
		const cursor = new Date(startMonday);
		while (cursor <= endSunday) {
			const cells: { iso: string | null; messages: number; tokens: number; show: boolean }[] = [];
			for (let r = 0; r < 7; r++) {
				const day = new Date(cursor);
				day.setDate(cursor.getDate() + r);
				const inMonth = day.getMonth() === month - 1 && day.getFullYear() === year;
				const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(
					day.getDate()
				).padStart(2, '0')}`;
				if (!inMonth) {
					cells.push({ iso: null, messages: 0, tokens: 0, show: false });
				} else {
					const row = byDate.get(iso);
					cells.push({
						iso,
						messages: row?.messages ?? 0,
						tokens: row?.tokens ?? 0,
						show: true
					});
				}
			}
			columns.push({ cells });
			cursor.setDate(cursor.getDate() + 7);
		}
		return columns;
	}

	async function loadHeatmap() {
		heatmapLoading = true;
		heatmapError = null;
		try {
			heatmapRows = await getUserActivityHeatmap(localStorage.token, heatmapYear);
		} catch (e: any) {
			heatmapError = e?.detail?.detail ?? e?.detail ?? 'Failed to load';
			heatmapRows = [];
		} finally {
			heatmapLoading = false;
		}
	}

	function onHeatmapYearSelectChange() {
		if (heatmapSelectStr === '__pick__') {
			showHeatmapYearPicker = true;
			heatmapSelectStr = String(heatmapYear);
			return;
		}
		heatmapYear = parseInt(heatmapSelectStr, 10);
		loadHeatmap();
	}

	function pickHeatmapYear(y: number) {
		heatmapYear = y;
		heatmapSelectStr = String(y);
		showHeatmapYearPicker = false;
		loadHeatmap();
	}

	function heatmapDateLabel(iso: string) {
		return dayjs(iso).format('MMMM D, YYYY');
	}

	function onHeatCellMove(
		e: MouseEvent,
		cell: { iso: string | null; messages: number; tokens: number; show: boolean }
	) {
		if (!cell.show || !cell.iso) {
			heatTooltip = null;
			return;
		}
		heatTooltip = {
			x: e.clientX,
			y: e.clientY,
			dateLabel: heatmapDateLabel(cell.iso),
			messages: cell.messages,
			tokens: cell.tokens,
			empty: cell.messages <= 0
		};
	}

	function onHeatCellLeave() {
		heatTooltip = null;
	}

	function destroyPie() {
		if (pieChart) {
			pieChart.destroy();
			pieChart = null;
		}
	}

	function destroyLine() {
		if (lineChart) {
			lineChart.destroy();
			lineChart = null;
		}
	}

	async function loadSummary() {
		summaryLoading = true;
		summaryError = null;
		try {
			summary = await getAnalyticsSummary(localStorage.token);
		} catch (e: any) {
			summaryError = e?.detail?.detail ?? e?.detail ?? 'Failed to load';
			summary = null;
		} finally {
			summaryLoading = false;
		}
	}

	async function loadTables() {
		tablesLoading = true;
		tablesError = null;
		try {
			const [mu, ua] = await Promise.all([
				getModelUsage(localStorage.token),
				getUserActivity(localStorage.token)
			]);
			modelUsageRows = mu;
			userActivityRows = ua;
		} catch (e: any) {
			tablesError = e?.detail?.detail ?? e?.detail ?? 'Failed to load';
			modelUsageRows = [];
			userActivityRows = [];
		} finally {
			tablesLoading = false;
		}
		// Pie canvas only mounts after loading finishes — build chart after DOM shows it.
		await tick();
		await tick();
		buildPieChart();
	}

	async function loadLineChartFilters() {
		try {
			const opts = await getLineChartFilterOptions(localStorage.token);
			lineChartUsers = opts.users ?? [];
			lineChartModels = opts.models ?? [];
			if (selectedUserId && !lineChartUsers.some((u) => u.id === selectedUserId)) {
				selectedUserId = '';
			}
			if (selectedModelId && !lineChartModels.some((m) => m.id === selectedModelId)) {
				selectedModelId = '';
			}
		} catch {
			lineChartUsers = [];
			lineChartModels = [];
		}
	}

	async function loadLineData() {
		lineLoading = true;
		lineError = null;
		const { start, end } = dateRange();
		try {
			lineRaw = await getUsageOverTime(localStorage.token, {
				metric,
				start_date: start,
				end_date: end,
				...(selectedUserId ? { user_id: selectedUserId } : {}),
				...(selectedModelId ? { model_id: selectedModelId } : {})
			});
			await tick();
			buildLineChart();
		} catch (e: any) {
			lineError = e?.detail?.detail ?? e?.detail ?? 'Failed to load';
			lineRaw = [];
			destroyLine();
		} finally {
			lineLoading = false;
		}
	}

	function buildPieChart() {
		if (!pieCanvas || modelUsageRows.length === 0) {
			destroyPie();
			pieSlices = [];
			return;
		}
		destroyPie();
		pieSlices = computePieSlices(modelUsageRows, $i18n.t('Others'));
		const labels = pieSlices.map((s) => s.label);
		const data = pieSlices.map((s) => s.messages);
		const colors = pieSlices.map((_, i) => PALETTE[i % PALETTE.length]);

		pieChart = new Chart(pieCanvas.getContext('2d')!, {
			type: 'doughnut',
			data: {
				labels,
				datasets: [
					{
						data,
						backgroundColor: colors,
						borderWidth: 0,
						hoverOffset: 6
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '62%',
				layout: { padding: 4 },
				animation: { duration: 400 },
				plugins: {
					legend: { display: false },
					tooltip: {
						backgroundColor: '#1f2937',
						padding: 10,
						titleFont: { size: 13, weight: '600' },
						bodyFont: { size: 12 },
						displayColors: false,
						callbacks: {
							title: (items) => {
								const i = items[0]?.dataIndex ?? 0;
								return pieSlices[i]?.label ?? '';
							},
							label: (ctx) => {
								const i = ctx.dataIndex ?? 0;
								const row = pieSlices[i];
								if (!row) return '';
								const share = row.sharePercent.toFixed(1);
								return [
									`${$i18n.t('Messages')}: ${row.messages.toLocaleString()}`,
									`${$i18n.t('Tokens')}: ${row.tokens.toLocaleString()}`,
									`${$i18n.t('Share')}: ${share}%`
								];
							}
						}
					}
				}
			}
		});
		requestAnimationFrame(() => pieChart?.resize());
	}

	function buildLineChart() {
		if (!lineCanvas) return;
		destroyLine();
		if (lineRaw.length === 0) return;
		const { start, end } = dateRange();
		const days = eachDayInclusive(start, end);

		const byDate = new Map<string, Map<string, number>>();
		for (const row of lineRaw) {
			if (!byDate.has(row.date)) byDate.set(row.date, new Map());
			byDate.get(row.date)!.set(row.model, row.count);
		}

		let modelIds: string[];
		if (selectedModelId) {
			modelIds = [selectedModelId];
		} else {
			const set = new Set<string>();
			for (const row of lineRaw) set.add(row.model);
			modelIds = Array.from(set).sort();
		}

		if (modelIds.length === 0) return;

		const datasets = modelIds.map((mid) => {
			const data = days.map((d) => byDate.get(d)?.get(mid) ?? 0);
			const labelRow = lineChartModels.find((m) => m.id === mid);
			const label =
				labelRow?.name ??
				modelUsageRows.find((r) => r.model_id === mid)?.model ??
				mid;
			return {
				label,
				data,
				borderColor: colorForModel(mid),
				backgroundColor: colorForModel(mid),
				tension: lineSmooth ? 0.35 : 0,
				fill: false,
				pointRadius: 0,
				pointHoverRadius: 0,
				pointBorderWidth: 0,
				pointBackgroundColor: 'transparent',
				pointBorderColor: 'transparent',
				borderWidth: 2
			};
		});

		lineChart = new Chart(lineCanvas.getContext('2d')!, {
			type: 'line',
			data: {
				labels: days.map(formatAxisDate),
				datasets
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: 'index', intersect: false },
				plugins: {
					legend: {
						display: false
					},
					tooltip: {
						mode: 'index',
						intersect: false
					}
				},
				scales: {
					x: {
						ticks: {
							maxRotation: 0,
							autoSkip: true,
							maxTicksLimit: 12
						},
						title: {
							display: true,
							text: $i18n.t('Date'),
							font: { size: 12, weight: '500' }
						},
						grid: { display: false }
					},
					y: {
						beginAtZero: true,
						title: {
							display: true,
							text: metric === 'messages' ? $i18n.t('Messages') : $i18n.t('Tokens'),
							font: { size: 12, weight: '500' },
							rotation: -90,
							align: 'center'
						},
						grid: { color: 'rgba(0,0,0,0.06)' }
					}
				}
			}
		});
	}

	function toggleSortModel(key: keyof ModelUsageRow) {
		if (modelSort.key === key) {
			modelSort = { key, dir: modelSort.dir === 'asc' ? 'desc' : 'asc' };
		} else {
			modelSort = { key, dir: 'desc' };
		}
	}

	function toggleSortUser(key: keyof UserActivityRow) {
		if (userSort.key === key) {
			userSort = { key, dir: userSort.dir === 'asc' ? 'desc' : 'asc' };
		} else {
			userSort = { key, dir: 'desc' };
		}
	}

	function cmpNum(a: number, b: number, dir: SortDir) {
		return dir === 'asc' ? a - b : b - a;
	}

	function cmpStr(a: string, b: string, dir: SortDir) {
		return dir === 'asc' ? a.localeCompare(b) : b.localeCompare(a);
	}

	$: sortedModelTable = [...modelUsageRows].sort((a, b) => {
		const k = modelSort.key;
		const dir = modelSort.dir;
		if (k === 'messages' || k === 'tokens' || k === 'share_percent')
			return cmpNum(a[k] as number, b[k] as number, dir);
		return cmpStr(String(a[k]), String(b[k]), dir);
	});

	$: sortedUserTable = [...userActivityRows].sort((a, b) => {
		const k = userSort.key;
		const dir = userSort.dir;
		if (k === 'messages' || k === 'tokens' || k === 'rank')
			return cmpNum(a[k] as number, b[k] as number, dir);
		return cmpStr(String(a[k]), String(b[k]), dir);
	});

	function exportLineCsv() {
		const { start, end } = dateRange();
		const days = eachDayInclusive(start, end);
		const modelIds = selectedModelId
			? [selectedModelId]
			: Array.from(new Set(lineRaw.map((r) => r.model))).sort();
		const header = ['Date', ...modelIds];
		const lines = [header.join(',')];
		const byDate = new Map<string, Map<string, number>>();
		for (const row of lineRaw) {
			if (!byDate.has(row.date)) byDate.set(row.date, new Map());
			byDate.get(row.date)!.set(row.model, row.count);
		}
		for (const d of days) {
			const cells = [d, ...modelIds.map((m) => String(byDate.get(d)?.get(m) ?? 0))];
			lines.push(cells.join(','));
		}
		const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = `analytics-line-${start}_${end}.csv`;
		a.click();
		URL.revokeObjectURL(a.href);
		lineExportOpen = false;
	}

	function exportLinePng() {
		if (!lineChart) return;
		const url = lineChart.toBase64Image('image/png', 1);
		const a = document.createElement('a');
		a.href = url;
		a.download = `analytics-line-${Date.now()}.png`;
		a.click();
		lineExportOpen = false;
	}

	function modelDisplayName(modelId: string) {
		const labelRow = lineChartModels.find((m) => m.id === modelId);
		return (
			labelRow?.name ??
			modelUsageRows.find((r) => r.model_id === modelId)?.model ??
			modelId
		);
	}

	function exportLineExcel() {
		const { start, end } = dateRange();
		const days = eachDayInclusive(start, end);
		const modelIds = selectedModelId
			? [selectedModelId]
			: Array.from(new Set(lineRaw.map((r) => r.model))).sort();
		const byDate = new Map<string, Map<string, number>>();
		for (const row of lineRaw) {
			if (!byDate.has(row.date)) byDate.set(row.date, new Map());
			byDate.get(row.date)!.set(row.model, row.count);
		}
		const header = ['Date', ...modelIds.map((id) => modelDisplayName(id))];
		const rows: (string | number)[][] = [header];
		for (const d of days) {
			rows.push([d, ...modelIds.map((m) => byDate.get(d)?.get(m) ?? 0)]);
		}
		const ws = XLSX.utils.aoa_to_sheet(rows);
		const wb = XLSX.utils.book_new();
		XLSX.utils.book_append_sheet(wb, ws, 'Usage');
		XLSX.writeFile(wb, `analytics-line-${start}_${end}.xlsx`);
		lineExportOpen = false;
	}

	function downloadBlob(blob: Blob, filename: string) {
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = filename;
		a.click();
		URL.revokeObjectURL(a.href);
	}

	function csvEscape(value: string | number) {
		const str = String(value ?? '');
		if (/[",\r\n]/.test(str)) {
			return `"${str.replaceAll('"', '""')}"`;
		}
		return str;
	}

	function getModelUsageExportRows() {
		return sortedModelTable.map((row, i) => [
			i + 1,
			row.model,
			row.messages,
			row.tokens,
			row.share_percent
		]);
	}

	function getUserActivityExportRows() {
		return sortedUserTable.map((row) => [row.rank, row.user, row.role, row.messages, row.tokens]);
	}

	function applyAutoSizeColumns(ws: XLSX.WorkSheet, rows: (string | number)[][]) {
		const maxCol = rows[0]?.length ?? 0;
		ws['!cols'] = Array.from({ length: maxCol }, (_, colIdx) => {
			const width = rows.reduce((max, row) => Math.max(max, String(row[colIdx] ?? '').length), 10);
			return { wch: Math.min(width + 2, 48) };
		});
	}

	function exportModelUsageCsv() {
		const date = dayjs().format('YYYY-MM-DD');
		const header = ['Rank', 'Model', 'Messages', 'Tokens', 'Usage Share (%)'];
		const rows = getModelUsageExportRows();
		const csv = [header, ...rows].map((r) => r.map(csvEscape).join(',')).join('\r\n');
		downloadBlob(
			new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }),
			`model-usage-${date}.csv`
		);
	}

	function exportUserActivityCsv() {
		const date = dayjs().format('YYYY-MM-DD');
		const header = ['Rank', 'User', 'Role', 'Messages', 'Tokens'];
		const rows = getUserActivityExportRows();
		const csv = [header, ...rows].map((r) => r.map(csvEscape).join(',')).join('\r\n');
		downloadBlob(
			new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }),
			`user-activity-${date}.csv`
		);
	}

	function exportModelUsageExcel() {
		const date = dayjs().format('YYYY-MM-DD');
		const header = ['Rank', 'Model', 'Messages', 'Tokens', 'Usage Share (%)'];
		const rows = [header, ...getModelUsageExportRows()];
		const ws = XLSX.utils.aoa_to_sheet(rows);
		applyAutoSizeColumns(ws, rows);
		const wb = XLSX.utils.book_new();
		XLSX.utils.book_append_sheet(wb, ws, 'Model Usage');
		XLSX.writeFile(wb, `model-usage-${date}.xlsx`);
	}

	function exportUserActivityExcel() {
		const date = dayjs().format('YYYY-MM-DD');
		const header = ['Rank', 'User', 'Role', 'Messages', 'Tokens'];
		const rows = [header, ...getUserActivityExportRows()];
		const ws = XLSX.utils.aoa_to_sheet(rows);
		applyAutoSizeColumns(ws, rows);
		const wb = XLSX.utils.book_new();
		XLSX.utils.book_append_sheet(wb, ws, 'User Activity');
		XLSX.writeFile(wb, `user-activity-${date}.xlsx`);
	}

	function exportModelUsagePdf() {
		const date = dayjs().format('YYYY-MM-DD');
		const timestamp = dayjs().format('YYYY-MM-DD HH:mm:ss');
		const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
		const header = ['Rank', 'Model', 'Messages', 'Tokens', 'Usage Share (%)'];
		doc.setFontSize(11);
		doc.text('Open WebUI Analytics', 40, 34);
		doc.setFontSize(14);
		doc.text('Model Usage Table', 40, 56);
		doc.setFontSize(10);
		doc.text(`Exported: ${timestamp}`, 40, 74);
		autoTable(doc, {
			startY: 86,
			head: [header],
			body: getModelUsageExportRows(),
			theme: 'grid',
			headStyles: { fillColor: [59, 75, 200] },
			styles: { fontSize: 9, halign: 'left' },
			columnStyles: {
				0: { halign: 'right' },
				2: { halign: 'right' },
				3: { halign: 'right' },
				4: { halign: 'right' }
			}
		});
		doc.save(`model-usage-${date}.pdf`);
	}

	function exportUserActivityPdf() {
		const date = dayjs().format('YYYY-MM-DD');
		const timestamp = dayjs().format('YYYY-MM-DD HH:mm:ss');
		const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
		const header = ['Rank', 'User', 'Role', 'Messages', 'Tokens'];
		doc.setFontSize(11);
		doc.text('Open WebUI Analytics', 40, 34);
		doc.setFontSize(14);
		doc.text('User Activity Table', 40, 56);
		doc.setFontSize(10);
		doc.text(`Exported: ${timestamp}`, 40, 74);
		autoTable(doc, {
			startY: 86,
			head: [header],
			body: getUserActivityExportRows(),
			theme: 'grid',
			headStyles: { fillColor: [59, 75, 200] },
			styles: { fontSize: 9, halign: 'left' },
			columnStyles: {
				0: { halign: 'right' },
				3: { halign: 'right' },
				4: { halign: 'right' }
			}
		});
		doc.save(`user-activity-${date}.pdf`);
	}

	async function handleTableExport(
		table: 'model-usage' | 'user-activity',
		format: 'pdf' | 'csv' | 'xlsx'
	) {
		if (tableExporting) return;
		tableExporting = true;
		tableExportOpen = false;
		try {
			if (table === 'model-usage') {
				if (format === 'pdf') exportModelUsagePdf();
				if (format === 'csv') exportModelUsageCsv();
				if (format === 'xlsx') exportModelUsageExcel();
			} else {
				if (format === 'pdf') exportUserActivityPdf();
				if (format === 'csv') exportUserActivityCsv();
				if (format === 'xlsx') exportUserActivityExcel();
			}
			toast.success($i18n.t('Export completed successfully.'));
		} catch (e) {
			toast.error($i18n.t('Export failed.'));
		} finally {
			tableExporting = false;
		}
	}

	function onDocClick(ev: MouseEvent) {
		const t = ev.target as HTMLElement;
		if (!t.closest?.('[data-dropdown="calendar"]')) showCalendar = false;
		if (!t.closest?.('[data-dropdown="line-export"]')) lineExportOpen = false;
		if (!t.closest?.('[data-dropdown="table-export"]')) tableExportOpen = false;
		if (!t.closest?.('[data-heatmap-year]')) showHeatmapYearPicker = false;
	}

	onMount(() => {
		Chart.register(...registerables);
		document.addEventListener('click', onDocClick);
		loadSummary();
		loadTables();
		loadHeatmap();
		(async () => {
			await loadLineChartFilters();
			await loadLineData();
		})();
		return () => document.removeEventListener('click', onDocClick);
	});

	onDestroy(() => {
		destroyPie();
		destroyLine();
	});

	$: calendarApplyInvalid =
		!!customStart &&
		!!customEnd &&
		dayjs.utc(customEnd).isBefore(dayjs.utc(customStart), 'day');
</script>

<div class="flex flex-col w-full max-w-[1400px] mx-auto gap-6 pb-8">
	{#if summaryLoading && !summary}
		<div class="animate-pulse space-y-3">
			<div class="h-9 w-48 bg-gray-200 dark:bg-gray-700 rounded" />
			<div class="h-4 w-full max-w-xl bg-gray-100 dark:bg-gray-800 rounded" />
		</div>
	{:else if summaryError && !summary}
		<div
			class="rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 px-4 py-3 flex flex-wrap items-center gap-3"
		>
			<span class="text-red-700 dark:text-red-300">{$i18n.t('Failed to load data.')}</span>
			<button
				type="button"
				class="text-sm font-medium px-3 py-1 rounded-lg bg-gray-900 text-white dark:bg-white dark:text-gray-900"
				on:click={() => loadSummary()}>{$i18n.t('Retry')}</button
			>
		</div>
	{:else if summary}
		<div>
			<h1 class="text-[28px] font-bold text-gray-900 dark:text-white tracking-tight">
				{$i18n.t('Analytics')}
			</h1>
			<p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
				{summary.messages.toLocaleString()}
				{$i18n.t('messages')}
				· {summary.tokens.toLocaleString()}
				{$i18n.t('tokens')}
				· {summary.chats.toLocaleString()}
				{$i18n.t('chats')}
				· {summary.users.toLocaleString()}
				{$i18n.t('users')}
				· US${fmtUsd(summary.estimated_cost)}
				({$i18n.t('Est. cost')})
				· {(summary.sensitive_upload_blocks_total ?? 0).toLocaleString()}
				{$i18n.t('blocked sensitive uploads')}
				({$i18n.t('Metadata')}: {(summary.sensitive_upload_blocks_metadata ?? 0).toLocaleString()},
				{$i18n.t('Content')}: {(summary.sensitive_upload_blocks_content ?? 0).toLocaleString()})
			</p>
		</div>
	{/if}

	<div
		class="rounded-[12px] bg-white dark:bg-gray-900 shadow-[0_1px_4px_rgba(0,0,0,0.08)] border border-gray-100 dark:border-gray-800 overflow-hidden"
	>
		<!-- Compact filters: same horizontal band as the line chart (70% column on lg) -->
		<div class="flex border-b border-gray-100 dark:border-gray-800 bg-[#fafafa]/40 dark:bg-gray-850/20">
			<div
				class="hidden lg:block lg:w-[30%] shrink-0 border-r border-gray-100 dark:border-gray-800"
				aria-hidden="true"
			></div>
			<div
				class="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5 px-4 py-2 lg:w-[70%] lg:px-6 relative z-20"
			>
				<select
					class="analytics-select analytics-filter-inline"
					bind:value={selectedUserId}
					on:change={() => loadLineData()}
					aria-label={$i18n.t('All Users')}
				>
					<option value="">{$i18n.t('All Users')}</option>
					{#each lineChartUsers as u}
						<option value={u.id}>{u.name}</option>
					{/each}
				</select>

				<select
					class="analytics-select analytics-filter-inline"
					bind:value={selectedModelId}
					on:change={() => loadLineData()}
					aria-label={$i18n.t('All Models')}
				>
					<option value="">{$i18n.t('All Models')}</option>
					{#each lineChartModels as m}
						<option value={m.id}>{m.name}</option>
					{/each}
				</select>

				<select
					class="analytics-select analytics-filter-inline"
					bind:value={metric}
					on:change={() => loadLineData()}
				>
					<option value="messages">{$i18n.t('Messages')}</option>
					<option value="tokens">{$i18n.t('Tokens')}</option>
				</select>

				<div class="relative" data-dropdown="calendar">
					<select
						class="analytics-select analytics-filter-inline"
						bind:value={timePreset}
						on:change={() => {
							if (timePreset === 'custom') {
								showCalendar = true;
							} else {
								showCalendar = false;
								loadLineData();
							}
						}}
					>
						<option value="7">{$i18n.t('Last 7 Days')}</option>
						<option value="20">{$i18n.t('Last 20 Days')}</option>
						<option value="30">{$i18n.t('Last 30 Days')}</option>
						<option value="all">{$i18n.t('All Time')}</option>
						<option value="custom">{$i18n.t('Custom Range')} →</option>
					</select>

					{#if showCalendar && timePreset === 'custom'}
						<div
							class="absolute right-0 mt-2 z-50 bg-white dark:bg-gray-850 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 w-[260px] text-sm"
						>
							<div class="flex flex-col gap-2">
								<label class="flex flex-col gap-1">
									<span class="text-gray-500 text-xs">{$i18n.t('Start Date')}</span>
									<input type="date" class="analytics-select py-1" bind:value={customStart} />
								</label>
								<label class="flex flex-col gap-1">
									<span class="text-gray-500 text-xs">{$i18n.t('End Date')}</span>
									<input type="date" class="analytics-select py-1" bind:value={customEnd} />
								</label>
								<div class="flex justify-end gap-2 mt-2">
									<button
										type="button"
										class="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-600"
										on:click={() => {
											showCalendar = false;
										}}>{$i18n.t('Cancel')}</button
									>
									<button
										type="button"
										disabled={calendarApplyInvalid || !customStart || !customEnd}
										class="px-3 py-1.5 rounded-lg bg-gray-900 text-white dark:bg-white dark:text-gray-900 disabled:opacity-40"
										on:click={() => {
											if (calendarApplyInvalid) return;
											showCalendar = false;
											loadLineData();
										}}>{$i18n.t('Apply')}</button
									>
								</div>
							</div>
						</div>
					{/if}
				</div>

				<div class="relative" data-dropdown="line-export">
					<button
						type="button"
						class="analytics-select analytics-filter-inline inline-flex flex-shrink-0 items-center justify-between gap-1.5"
						on:click|stopPropagation={() => (lineExportOpen = !lineExportOpen)}
					>
						<Download className="size-3.5 shrink-0" />
						<span>{$i18n.t('Export')}</span>
						<svg class="size-3.5 shrink-0 text-gray-400" fill="currentColor" viewBox="0 0 20 20"
							><path
								d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.24 4.5a.75.75 0 01-1.08 0l-4.24-4.5a.75.75 0 01.02-1.06z"
							/></svg
						>
					</button>
					{#if lineExportOpen}
						<div
							class="absolute right-0 mt-1 z-50 bg-white dark:bg-gray-850 border border-gray-200 dark:border-gray-700 rounded-lg shadow-md py-1 min-w-[160px]"
						>
							<button
								type="button"
								class="block w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm"
								on:click|stopPropagation={() => exportLineCsv()}>{$i18n.t('Export as CSV')}</button
							>
							<button
								type="button"
								class="block w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm"
								on:click|stopPropagation={() => exportLinePng()}>{$i18n.t('Export as PNG')}</button
							>
							<button
								type="button"
								class="block w-full text-left px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm"
								on:click|stopPropagation={() => exportLineExcel()}>{$i18n.t('Export as Excel')}</button
							>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="flex flex-col lg:flex-row min-h-[360px]">
			<div
				class="lg:w-[30%] border-b lg:border-b-0 lg:border-r border-gray-100 dark:border-gray-800 p-6 flex flex-col min-h-[280px] lg:min-h-0"
			>
				<h2 class="text-base font-semibold text-gray-900 dark:text-white mb-4">
					{$i18n.t('Model Usage')}
				</h2>
				{#if tablesLoading}
					<div class="flex-1 flex items-center justify-center min-h-[240px]">
						<div class="animate-spin rounded-full h-10 w-10 border-2 border-gray-300 border-t-gray-600" />
					</div>
				{:else if tablesError}
					<p class="text-sm text-red-600">{$i18n.t('Failed to load data.')}</p>
				{:else if modelUsageRows.length === 0}
					<div class="flex-1 flex items-center justify-center text-gray-500 text-sm min-h-[240px]">
						{$i18n.t('No data available')}
					</div>
				{:else}
					<div class="flex flex-1 flex-col items-center justify-center min-h-[220px] py-2">
						<div class="relative h-[200px] w-[200px] shrink-0 mx-auto">
							<canvas bind:this={pieCanvas} class="block h-full w-full" />
						</div>
					</div>
				{/if}
			</div>

			<div class="lg:w-[70%] p-6 flex flex-col">
				<div class="flex flex-wrap items-start justify-between gap-3 mb-4">
					<h2 class="text-base font-semibold text-gray-900 dark:text-white">
						{$i18n.t('Model usage over time')}
					</h2>
					<div
						class="inline-flex rounded-full border border-gray-200 dark:border-gray-700 p-0.5 text-xs font-medium"
					>
						<button
							type="button"
							class="px-3 py-1 rounded-full transition {lineSmooth
								? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
								: 'text-gray-600 dark:text-gray-400'}"
							on:click={async () => {
								lineSmooth = true;
								await tick();
								buildLineChart();
							}}>{$i18n.t('Smooth')}</button
						>
						<button
							type="button"
							class="px-3 py-1 rounded-full transition {!lineSmooth
								? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
								: 'text-gray-600 dark:text-gray-400'}"
							on:click={async () => {
								lineSmooth = false;
								await tick();
								buildLineChart();
							}}>{$i18n.t('Straight')}</button
						>
					</div>
				</div>

				<div class="relative flex-1 min-h-[280px]">
					{#if lineLoading}
						<div class="absolute inset-0 z-10 flex items-center justify-center bg-white/70 dark:bg-gray-900/70">
							<div
								class="animate-spin rounded-full h-10 w-10 border-2 border-gray-300 border-t-gray-600"
							/>
						</div>
					{/if}
					{#if lineError}
						<div class="flex items-center justify-center h-full text-red-600 text-sm px-4">
							{$i18n.t('Failed to load data.')}
							<button type="button" class="ml-2 underline" on:click={() => loadLineData()}
								>{$i18n.t('Retry')}</button
							>
						</div>
					{:else if !lineLoading && lineRaw.length === 0}
						<div class="flex items-center justify-center h-full text-gray-500 text-sm">
							{$i18n.t('No data available')}
						</div>
					{:else}
						<canvas bind:this={lineCanvas} class="w-full h-full" />
					{/if}
				</div>
			</div>
		</div>
	</div>

	<div
		class="w-full rounded-[12px] bg-white dark:bg-gray-900 shadow-[0_1px_4px_rgba(0,0,0,0.08)] border border-gray-100 dark:border-gray-800 p-6"
	>
		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-8 lg:items-start">
		<div class="min-w-0 flex flex-col">
			<div class="mb-3 flex min-h-[2.25rem] items-center justify-between gap-2 min-w-0">
				<h3 class="min-w-0 flex-1 truncate pr-2 text-base font-semibold text-gray-900 dark:text-white">
					{$i18n.t('Model Usage Table')}
				</h3>
				<div class="flex shrink-0 items-center gap-0.5">
					<button
						type="button"
						class="text-gray-400 hover:text-gray-600 p-1"
						aria-label={$i18n.t('Expand')}
						on:click={() => (modelModalOpen = true)}
					>
						<ArrowsPointingOut className="size-4" />
					</button>
				</div>
			</div>
			<div class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
				<div class="max-h-[280px] overflow-x-auto overflow-y-auto">
					<table class="analytics-table w-full min-w-[520px] table-fixed border-collapse text-sm">
						<colgroup>
							<col style="width: 44px" />
							<col />
							<col style="width: 112px" />
							<col style="width: 112px" />
							<col style="width: 104px" />
						</colgroup>
						<thead
							class="sticky top-0 z-10 border-b border-gray-200 bg-[#fafafa] dark:border-gray-700 dark:bg-gray-850"
						>
							<tr>
								<th class="px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200">#</th>
								<th
									class="min-w-0 cursor-pointer px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortModel('model')}>{$i18n.t('Model')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortModel('messages')}>{$i18n.t('Messages')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortModel('tokens')}>{$i18n.t('Tokens')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortModel('share_percent')}>{$i18n.t('Usage Share')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each sortedModelTable as row, i}
								<tr
									class="border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-850/50"
								>
									<td class="px-3 py-2.5 text-left text-gray-500 tabular-nums">{i + 1}</td>
									<td class="min-w-0 truncate px-3 py-2.5 text-left" title={row.model}>{row.model}</td>
									<td class="px-3 py-2.5 text-right tabular-nums">{row.messages.toLocaleString()}</td>
									<td class="px-3 py-2.5 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
									<td class="px-3 py-2.5 text-right tabular-nums">{row.share_percent}%</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</div>

		<div class="min-w-0 flex flex-col">
			<div class="mb-3 flex min-h-[2.25rem] items-center justify-between gap-2 min-w-0">
				<h3 class="min-w-0 flex-1 truncate pr-2 text-base font-semibold text-gray-900 dark:text-white">
					{$i18n.t('User Activity Table')}
				</h3>
				<div class="flex shrink-0 items-center gap-0.5">
					<button
						type="button"
						class="text-gray-400 hover:text-gray-600 p-1"
						aria-label={$i18n.t('Expand')}
						on:click={() => (userModalOpen = true)}
					>
						<ArrowsPointingOut className="size-4" />
					</button>
					<div class="relative shrink-0" data-dropdown="table-export">
						<button
							type="button"
							title={$i18n.t('Export Data')}
							aria-label={$i18n.t('Export Data')}
							disabled={tableExporting}
							class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-transparent text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
							on:click|stopPropagation={() => (tableExportOpen = !tableExportOpen)}
						>
							{#if tableExporting}
								<div class="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
							{:else}
								<Download className="size-4" />
							{/if}
						</button>
						{#if tableExportOpen}
							<div
								class="absolute right-0 top-full mt-2 z-50 w-max max-w-[min(260px,calc(100vw-3rem))] rounded-lg border border-gray-200 bg-white py-1 shadow-md dark:border-gray-700 dark:bg-gray-850"
							>
								<div class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
									{$i18n.t('Model Usage Table')}
								</div>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('model-usage', 'pdf')}
									>{$i18n.t('Export Model Usage as PDF')}</button
								>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('model-usage', 'csv')}
									>{$i18n.t('Export Model Usage as CSV')}</button
								>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('model-usage', 'xlsx')}
									>{$i18n.t('Export Model Usage as Excel')}</button
								>
								<div class="my-1 border-t border-gray-100 dark:border-gray-700"></div>
								<div class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
									{$i18n.t('User Activity Table')}
								</div>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('user-activity', 'pdf')}
									>{$i18n.t('Export User Activity as PDF')}</button
								>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('user-activity', 'csv')}
									>{$i18n.t('Export User Activity as CSV')}</button
								>
								<button
									type="button"
									disabled={tableExporting}
									class="block w-full whitespace-normal px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
									on:click|stopPropagation={() => handleTableExport('user-activity', 'xlsx')}
									>{$i18n.t('Export User Activity as Excel')}</button
								>
							</div>
						{/if}
					</div>
				</div>
			</div>
			<div class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
				<div class="max-h-[280px] overflow-x-auto overflow-y-auto">
					<table class="analytics-table w-full min-w-[480px] table-fixed border-collapse text-sm">
						<colgroup>
							<col style="width: 44px" />
							<col />
							<col style="width: 96px" />
							<col style="width: 112px" />
							<col style="width: 112px" />
						</colgroup>
						<thead
							class="sticky top-0 z-10 border-b border-gray-200 bg-[#fafafa] dark:border-gray-700 dark:bg-gray-850"
						>
							<tr>
								<th class="px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200">#</th>
								<th
									class="min-w-0 cursor-pointer px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortUser('user')}>{$i18n.t('User')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortUser('role')}>{$i18n.t('Role')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortUser('messages')}>{$i18n.t('Messages')}</th
								>
								<th
									class="cursor-pointer px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
									on:click={() => toggleSortUser('tokens')}>{$i18n.t('Tokens')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each sortedUserTable as row}
								<tr
									class="border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-850/50"
								>
									<td class="px-3 py-2.5 text-left text-gray-500 tabular-nums">{row.rank}</td>
									<td class="min-w-0 truncate px-3 py-2.5 text-left" title={row.user}>{row.user}</td>
									<td class="px-3 py-2.5 text-left">
										<span
											class="inline-block max-w-full truncate px-2 py-0.5 rounded text-xs font-medium {row.role ===
											'admin'
												? 'bg-gray-800 text-white'
												: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'}"
											title={row.role}
										>
											{row.role}
										</span>
									</td>
									<td class="px-3 py-2.5 text-right tabular-nums">{row.messages.toLocaleString()}</td>
									<td class="px-3 py-2.5 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</div>
		</div>
	</div>

	<div
		class="w-full rounded-[12px] bg-white dark:bg-gray-900 shadow-[0_1px_4px_rgba(0,0,0,0.08)] border border-gray-100 dark:border-gray-800 p-6 relative"
	>
		<div class="flex flex-wrap items-start justify-between gap-3 mb-6">
			<h2 class="text-[18px] font-bold text-gray-900 dark:text-white">
				{$i18n.t('User Activity')}
			</h2>
			<div class="relative flex items-center gap-2" data-heatmap-year>
				<select
					class="heatmap-year-select"
					bind:value={heatmapSelectStr}
					on:change={onHeatmapYearSelectChange}
					aria-label={$i18n.t('Year')}
				>
					{#each heatmapYearOptions as y}
						<option value={String(y)}>{y}</option>
					{/each}
					<option value="__pick__">{$i18n.t('Select year')}</option>
				</select>

				{#if showHeatmapYearPicker}
					<div
						class="absolute right-0 top-full mt-2 z-[120] bg-white dark:bg-gray-850 border border-[#e0e0e0] dark:border-gray-700 rounded-lg shadow-lg p-3 w-[220px] max-h-[240px] overflow-y-auto"
						role="dialog"
					>
						<div class="text-xs font-medium text-gray-500 mb-2">{$i18n.t('Select year')}</div>
						<div class="grid grid-cols-4 gap-1.5">
							{#each Array.from({ length: HEATMAP_CY - 2000 + 1 }, (_, i) => HEATMAP_CY - i) as y}
								<button
									type="button"
									class="py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 {y ===
									heatmapYear
										? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 border-transparent'
										: ''}"
									on:click|stopPropagation={() => pickHeatmapYear(y)}>{y}</button
								>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>

		{#if heatmapLoading}
			<div class="overflow-x-auto pb-2">
				<div class="flex gap-8 min-w-max">
					{#each MONTH_LABELS as _label}
						<div class="flex flex-col gap-2">
							<div class="h-3 w-10 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
							<div class="flex gap-[3px]">
								{#each Array(4) as _}
									<div class="grid grid-rows-7 gap-[3px]">
										{#each Array(7) as __}
											<div class="w-[14px] h-[14px] rounded-[3px] bg-gray-200 dark:bg-gray-700 animate-pulse" />
										{/each}
									</div>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{:else if heatmapError}
			<p class="text-sm text-red-600">
				{$i18n.t('Failed to load data.')}
				<button type="button" class="underline ml-2" on:click={() => loadHeatmap()}
					>{$i18n.t('Retry')}</button
				>
			</p>
		{:else}
			<div class="overflow-x-auto pb-2 -mx-1 px-1">
				<div class="flex gap-8 min-w-max">
					{#each MONTH_LABELS as monthLabel, mi}
						{@const monthNum = mi + 1}
						{@const cols = buildMonthColumns(heatmapYear, monthNum, heatmapByDate)}
						<div class="flex flex-col flex-shrink-0">
							<div
								class="text-[12px] font-medium text-[#999] dark:text-gray-500 mb-2 text-left leading-none"
							>
								{monthLabel}
							</div>
							<div class="flex gap-[3px] items-start">
								{#each cols as col}
									<div class="grid grid-rows-7 gap-[3px]">
										{#each col.cells as cell}
											{#if cell.show}
												<button
													type="button"
													class="w-[14px] h-[14px] rounded-[3px] transition-colors duration-150 hover:ring-1 hover:ring-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-400"
													style="background-color: {heatBg(cell.messages)};"
													aria-label={cell.iso ?? ''}
													on:mousemove={(e) => onHeatCellMove(e, cell)}
													on:mouseleave={onHeatCellLeave}
												/>
											{:else}
												<div class="w-[14px] h-[14px] rounded-[3px] pointer-events-none opacity-0" />
											{/if}
										{/each}
									</div>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			</div>

			<div class="flex justify-end mt-4 items-center gap-2 text-[11px] text-[#999] dark:text-gray-500">
				<span>{$i18n.t('Less')}</span>
				<div class="flex gap-0.5 items-center">
					{#each HEAT_COLORS as c}
						<span class="w-[10px] h-[10px] rounded-sm shrink-0" style="background-color: {c};" />
					{/each}
				</div>
				<span>{$i18n.t('More')}</span>
			</div>
		{/if}
	</div>
</div>

{#if heatTooltip}
	<div
		class="fixed z-[200] pointer-events-none rounded-md bg-gray-900 text-white text-xs px-2.5 py-2 shadow-xl max-w-[220px]"
		style="left: {heatTooltip.x + 12}px; top: {heatTooltip.y + 12}px;"
	>
		<div class="font-semibold mb-1">{heatTooltip.dateLabel}</div>
		{#if heatTooltip.empty}
			<div>{$i18n.t('No activity')}</div>
		{:else}
			<div>{$i18n.t('Messages')}: {heatTooltip.messages.toLocaleString()}</div>
			<div>{$i18n.t('Tokens')}: {heatTooltip.tokens.toLocaleString()}</div>
		{/if}
	</div>
{/if}

{#if modelModalOpen}
	<div
		class="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4"
		role="presentation"
		on:click={() => (modelModalOpen = false)}
	>
		<div
			class="bg-white dark:bg-gray-900 rounded-xl shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col"
			role="dialog"
			on:click|stopPropagation
		>
			<div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
				<h3 class="font-semibold text-lg">{$i18n.t('Model Usage Table')}</h3>
				<button
					type="button"
					class="text-gray-500 hover:text-gray-800 text-xl leading-none px-2"
					on:click={() => (modelModalOpen = false)}>×</button
				>
			</div>
			<div class="overflow-auto flex-1 p-4">
				<table class="analytics-table w-full table-fixed border-collapse text-sm">
					<colgroup>
						<col style="width: 44px" />
						<col />
						<col style="width: 112px" />
						<col style="width: 112px" />
						<col style="width: 104px" />
					</colgroup>
					<thead class="sticky top-0 z-10 border-b border-gray-200 bg-[#fafafa] dark:border-gray-700 dark:bg-gray-850">
						<tr>
							<th class="px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200">#</th>
							<th class="min-w-0 px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Model')}</th
							>
							<th class="px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Messages')}</th
							>
							<th class="px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Tokens')}</th
							>
							<th class="px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Usage Share')}</th
							>
						</tr>
					</thead>
					<tbody>
						{#each sortedModelTable as row, i}
							<tr class="border-t border-gray-100 dark:border-gray-800">
								<td class="px-3 py-2.5 text-left text-gray-500 tabular-nums">{i + 1}</td>
								<td class="min-w-0 truncate px-3 py-2.5 text-left" title={row.model}>{row.model}</td>
								<td class="px-3 py-2.5 text-right tabular-nums">{row.messages.toLocaleString()}</td>
								<td class="px-3 py-2.5 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
								<td class="px-3 py-2.5 text-right tabular-nums">{row.share_percent}%</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	</div>
{/if}

{#if userModalOpen}
	<div
		class="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4"
		on:click={() => (userModalOpen = false)}
	>
		<div
			class="bg-white dark:bg-gray-900 rounded-xl shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col"
			on:click|stopPropagation
		>
			<div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
				<h3 class="font-semibold text-lg">{$i18n.t('User Activity')}</h3>
				<button
					type="button"
					class="text-gray-500 hover:text-gray-800 text-xl leading-none px-2"
					on:click={() => (userModalOpen = false)}>×</button
				>
			</div>
			<div class="overflow-auto flex-1 p-4">
				<table class="analytics-table w-full table-fixed border-collapse text-sm">
					<colgroup>
						<col style="width: 44px" />
						<col />
						<col style="width: 96px" />
						<col style="width: 112px" />
						<col style="width: 112px" />
					</colgroup>
					<thead class="sticky top-0 z-10 border-b border-gray-200 bg-[#fafafa] dark:border-gray-700 dark:bg-gray-850">
						<tr>
							<th class="px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200">#</th>
							<th class="min-w-0 px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('User')}</th
							>
							<th class="px-3 py-2.5 text-left font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Role')}</th
							>
							<th class="px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Messages')}</th
							>
							<th class="px-3 py-2.5 text-right font-semibold text-gray-700 dark:text-gray-200"
								>{$i18n.t('Tokens')}</th
							>
						</tr>
					</thead>
					<tbody>
						{#each sortedUserTable as row}
							<tr class="border-t border-gray-100 dark:border-gray-800">
								<td class="px-3 py-2.5 text-left text-gray-500 tabular-nums">{row.rank}</td>
								<td class="min-w-0 truncate px-3 py-2.5 text-left" title={row.user}>{row.user}</td>
								<td class="px-3 py-2.5 text-left">
									<span
										class="inline-block max-w-full truncate px-2 py-0.5 rounded text-xs font-medium {row.role ===
										'admin'
											? 'bg-gray-800 text-white'
											: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'}"
										title={row.role}
									>
										{row.role}
									</span>
								</td>
								<td class="px-3 py-2.5 text-right tabular-nums">{row.messages.toLocaleString()}</td>
								<td class="px-3 py-2.5 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	</div>
{/if}

<style lang="postcss">
	.analytics-select {
		@apply bg-white dark:bg-gray-900 border border-[#e0e0e0] dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 appearance-none cursor-pointer;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23999'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.6rem center;
		background-size: 1rem;
		padding-right: 2rem;
		min-height: 38px;
	}
	/* Compact dropdowns in line-chart filter strip — stay within ~70% column */
	.analytics-filter-inline {
		flex: 1 1 auto;
		min-width: 0;
		max-width: 158px;
		min-height: 32px;
		padding-top: 0.375rem;
		padding-bottom: 0.375rem;
		padding-left: 0.5rem;
		padding-right: 1.75rem;
		font-size: 0.75rem;
		line-height: 1.25rem;
	}
	@media (max-width: 1023px) {
		.analytics-filter-inline {
			max-width: min(158px, calc(50vw - 2rem));
		}
	}
	.analytics-table tbody tr td {
		@apply align-middle;
	}

	.heatmap-year-select {
		@apply bg-white dark:bg-gray-900 border border-[#e0e0e0] dark:border-gray-700 rounded-lg text-sm text-gray-800 dark:text-gray-100 appearance-none cursor-pointer;
		padding: 6px 12px;
		padding-right: 2rem;
		min-height: 32px;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23999'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.5rem center;
		background-size: 1rem;
	}
</style>
