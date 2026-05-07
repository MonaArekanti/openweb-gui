<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import dayjs from 'dayjs';
	import utc from 'dayjs/plugin/utc';

	import { getUsers } from '$lib/apis/users';
	import {
		getTokensSummary,
		getTokensDaily,
		getModelTokenBars,
		getTokenBreakdown,
		type TokensSummary,
		type TokensDaily,
		type ModelBarRow,
		type BreakdownRow
	} from '$lib/apis/admin_tokens';

	import ArrowsPointingOut from '$lib/components/icons/ArrowsPointingOut.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	dayjs.extend(utc);

	const i18n = getContext('i18n');

	type BarPreset = '7' | '20' | '30' | 'all' | 'custom';
	type ModelUsageRow = { model_id: string; model_name: string; tokens: number; price: number };

	let summary: TokensSummary | null = null;
	let summaryLoading = true;
	let summaryError: string | null = null;

	let daily: TokensDaily | null = null;
	let dailyLoading = true;
	let dailyError: string | null = null;

	let displayTokens = 0;
	let displayCost = 0;
	let displayAvg = 0;

	let barPreset: BarPreset = '30';
	let barCustomStart = '';
	let barCustomEnd = '';
	let showBarCalendar = false;

	let modelUsageRows: ModelUsageRow[] = [];
	let barsLoading = true;
	let barsError: string | null = null;
	let barTickKey = 0;
	let hoverGroupId: string | null = null;
	let hoverGroupIdModal: string | null = null;
	let showChartModal = false;

	/** All models returned by API (used for expanded chart) */
	let modelUsageRowsAll: ModelUsageRow[] = [];

	const MODELS_LIMIT = 8;
	const CHART_HEIGHT = 280;
	/** Modal chart plot height (matches bar math + container) */
	const CHART_HEIGHT_MODAL = 560;
	const TABLE_SCROLL_MAX_ROWS = 6;

	let tableUserId = '';
	let breakdownRows: BreakdownRow[] = [];
	let tableLoading = true;
	let tableError: string | null = null;

	let adminUsers: { id: string; name: string; email?: string }[] = [];

	type SortKey = 'model_name' | 'total_tokens' | 'price_per_1k_usd' | 'total_cost_usd';
	let sortKey: SortKey = 'total_tokens';
	let sortDir: 'asc' | 'desc' = 'desc';

	let rafId = 0;

	function fmtInt(n: number) {
		return Math.round(n).toLocaleString();
	}

	function fmtUsd3(n: number) {
		return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
	}

	function fmtUsdMoney(n: number) {
		return '$' + n.toFixed(3);
	}

	function fmtUsd4(n: number) {
		return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
	}

	function fmtAxisToken(n: number) {
		if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
		if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
		return String(Math.round(n));
	}

	function cancelCountUp() {
		if (rafId) cancelAnimationFrame(rafId);
		rafId = 0;
	}

	function countUpTriple(
		from: { a: number; b: number; c: number },
		to: { a: number; b: number; c: number },
		set: (v: { a: number; b: number; c: number }) => void,
		duration = 850
	) {
		cancelCountUp();
		const t0 = performance.now();
		function frame(now: number) {
			const p = Math.min(1, (now - t0) / duration);
			const ease = 1 - Math.pow(1 - p, 3);
			set({
				a: from.a + (to.a - from.a) * ease,
				b: from.b + (to.b - from.b) * ease,
				c: from.c + (to.c - from.c) * ease
			});
			if (p < 1) rafId = requestAnimationFrame(frame);
			else rafId = 0;
		}
		rafId = requestAnimationFrame(frame);
	}

	function barDateRange(): { start: string; end: string } {
		const end = dayjs.utc().format('YYYY-MM-DD');
		if (barPreset === 'custom') {
			if (barCustomStart && barCustomEnd) {
				return { start: barCustomStart, end: barCustomEnd };
			}
			const start = dayjs.utc().subtract(29, 'day').format('YYYY-MM-DD');
			return { start, end };
		}
		if (barPreset === 'all') {
			return { start: '2020-01-01', end };
		}
		const daysBack =
			barPreset === '7' ? 6 : barPreset === '20' ? 19 : 29;
		const start = dayjs.utc().subtract(daysBack, 'day').format('YYYY-MM-DD');
		return { start, end };
	}

	function buildUsageRows(tokensRows: ModelBarRow[], priceRows: ModelBarRow[]): ModelUsageRow[] {
		const byId = new Map<string, ModelUsageRow>();
		for (const r of tokensRows) {
			byId.set(r.model_id, {
				model_id: r.model_id,
				model_name: r.model_name,
				tokens: Number(r.value) || 0,
				price: 0
			});
		}
		for (const r of priceRows) {
			const ex = byId.get(r.model_id);
			if (ex) {
				ex.price = Number(r.value) || 0;
				if (!ex.model_name) ex.model_name = r.model_name;
			} else {
				byId.set(r.model_id, {
					model_id: r.model_id,
					model_name: r.model_name,
					tokens: 0,
					price: Number(r.value) || 0
				});
			}
		}
		return [...byId.values()].sort((a, b) => b.tokens - a.tokens);
	}

	async function loadSummaryBlock() {
		summaryLoading = true;
		summaryError = null;
		try {
			const [s, d] = await Promise.all([
				getTokensSummary(localStorage.token),
				getTokensDaily(localStorage.token)
			]);
			summary = s;
			daily = d;
			countUpTriple(
				{ a: displayTokens, b: displayCost, c: displayAvg },
				{
					a: s.total_tokens,
					b: s.total_estimated_cost_usd,
					c: s.avg_tokens_per_message
				},
				(v) => {
					displayTokens = v.a;
					displayCost = v.b;
					displayAvg = v.c;
				}
			);
		} catch (e: unknown) {
			summaryError = typeof e === 'object' && e && 'detail' in e ? String((e as { detail: unknown }).detail) : 'Failed to load';
			dailyError = summaryError;
		} finally {
			summaryLoading = false;
			dailyLoading = false;
		}
	}

	async function loadBars() {
		barsLoading = true;
		barsError = null;
		const r = barDateRange();
		if (barPreset === 'custom' && (!barCustomStart || !barCustomEnd || barCustomEnd < barCustomStart)) {
			barsLoading = false;
			return;
		}
		try {
			const [currentTokenRows, currentPriceRows] = await Promise.all([
				getModelTokenBars(localStorage.token, {
					start_date: r.start,
					end_date: r.end,
					metric: 'tokens'
				}),
				getModelTokenBars(localStorage.token, {
					start_date: r.start,
					end_date: r.end,
					metric: 'price'
				})
			]);
			const fullRows = buildUsageRows(currentTokenRows, currentPriceRows);
			modelUsageRowsAll = fullRows;
			modelUsageRows = fullRows.slice(0, MODELS_LIMIT);
			hoverGroupId = null;
			hoverGroupIdModal = null;
			barTickKey += 1;
		} catch (e: unknown) {
			barsError = typeof e === 'object' && e && 'detail' in e ? String((e as { detail: unknown }).detail) : 'Failed to load';
			modelUsageRows = [];
			modelUsageRowsAll = [];
		} finally {
			barsLoading = false;
		}
	}

	async function loadBreakdown() {
		tableLoading = true;
		tableError = null;
		try {
			const res = await getTokenBreakdown(
				localStorage.token,
				tableUserId || undefined
			);
			breakdownRows = res.rows ?? [];
		} catch (e: unknown) {
			tableError = typeof e === 'object' && e && 'detail' in e ? String((e as { detail: unknown }).detail) : 'Failed to load';
			breakdownRows = [];
		} finally {
			tableLoading = false;
		}
	}

	function retryAll() {
		loadSummaryBlock();
		loadBars();
		loadBreakdown();
	}

	function toggleSort(key: SortKey) {
		if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDir = key === 'model_name' ? 'asc' : 'desc';
		}
	}

	function cmpRows(a: BreakdownRow, b: BreakdownRow): number {
		const mul = sortDir === 'asc' ? 1 : -1;
		if (sortKey === 'model_name') {
			return mul * a.model_name.localeCompare(b.model_name);
		}
		const va =
			sortKey === 'total_tokens'
				? a.total_tokens
				: sortKey === 'price_per_1k_usd'
					? (a.price_per_1k_usd ?? -1)
					: (a.total_cost_usd ?? -1);
		const vb =
			sortKey === 'total_tokens'
				? b.total_tokens
				: sortKey === 'price_per_1k_usd'
					? (b.price_per_1k_usd ?? -1)
					: (b.total_cost_usd ?? -1);
		return mul * (Number(va) - Number(vb));
	}

	$: sortedBreakdown = [...breakdownRows].sort(cmpRows);
	$: breakdownTableScroll = sortedBreakdown.length > TABLE_SCROLL_MAX_ROWS;

	function handleWindowClick(e: MouseEvent) {
		const t = e.target;
		const el = t instanceof Element ? t : (t as Node).parentElement;
		if (!el) return;
		if (
			showBarCalendar &&
			!el.closest('[data-bar-calendar-root]') &&
			!el.closest('[data-bar-calendar-root-modal]')
		)
			showBarCalendar = false;
	}

	function handleChartModalKeydown(e: KeyboardEvent) {
		if (e.key !== 'Escape' || !showChartModal) return;
		showChartModal = false;
	}

	function applyCustomBarRange() {
		if (!barCustomStart || !barCustomEnd || barCustomEnd < barCustomStart) return;
		showBarCalendar = false;
		barPreset = 'custom';
		loadBars();
	}

	function handleVisibilityChange() {
		if (typeof document === 'undefined' || document.visibilityState !== 'visible') return;
		loadSummaryBlock();
		loadBars();
		loadBreakdown();
	}

	$: usageRowsTop = modelUsageRows.slice(0, MODELS_LIMIT);
	$: usagePageMaxTokens = Math.max(1, ...usageRowsTop.map((r) => r.tokens));
	$: usageYAxisMax = (() => {
		const roughStep = Math.max(1, (usagePageMaxTokens * 1.2) / 4);
		const magnitude = 10 ** Math.floor(Math.log10(roughStep));
		const niceStep = Math.ceil(roughStep / magnitude) * magnitude;
		return niceStep * 4;
	})();
	$: usageYAxisTicks = [0, 1, 2, 3, 4].map((n) => (usageYAxisMax / 4) * n).reverse();

	$: modalPageMaxTokens = Math.max(1, ...modelUsageRowsAll.map((r) => r.tokens));
	$: modalYAxisMax = (() => {
		const roughStep = Math.max(1, (modalPageMaxTokens * 1.2) / 4);
		const magnitude = 10 ** Math.floor(Math.log10(roughStep));
		const niceStep = Math.ceil(roughStep / magnitude) * magnitude;
		return niceStep * 4;
	})();
	$: modalYAxisTicks = [0, 1, 2, 3, 4].map((n) => (modalYAxisMax / 4) * n).reverse();

	function shortModelName(name: string): string {
		if ((name ?? '').length <= 10) return name;
		return name.slice(0, 10) + '...';
	}

	function barHeightPx(v: number, maxV: number, chartHeight: number): number {
		if (maxV <= 0) return 4;
		const plotH = chartHeight - 22;
		const h = (Math.max(0, v) / maxV) * plotH;
		return Math.max(4, Math.min(plotH, h));
	}

	onMount(async () => {
		window.addEventListener('click', handleWindowClick);
		document.addEventListener('visibilitychange', handleVisibilityChange);
		try {
			adminUsers = (await getUsers(localStorage.token)) ?? [];
		} catch {
			adminUsers = [];
		}
		await loadSummaryBlock();
		await Promise.all([loadBars(), loadBreakdown()]);
		return () => {
			window.removeEventListener('click', handleWindowClick);
			document.removeEventListener('visibilitychange', handleVisibilityChange);
			cancelCountUp();
		};
	});
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleChartModalKeydown} />

<div class="tokens-admin pb-12 bg-[#f9f9f9] dark:bg-gray-900 min-h-full -mx-[16px] px-4 md:px-6 pt-2">
	<h1 class="text-[28px] font-bold text-gray-900 dark:text-white mb-8">
		{$i18n.t('Token Usage')}
	</h1>

	{#if summaryError && !summary}
		<div
			class="mb-8 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200 flex flex-wrap items-center gap-3"
		>
			<span>{$i18n.t('Failed to load. Retry.')}</span>
			<button
				type="button"
				class="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700"
				on:click={retryAll}>{$i18n.t('Retry')}</button
			>
		</div>
	{/if}

	<!-- Ultra-compact stat row -->
	<div class="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-live="polite">
		<div class="h-[72px] flex items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850">
			<div class="h-full w-[3px] shrink-0 bg-[#2EC4B6]"></div>
			<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
				<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">TOTAL TOKENS</div>
				{#if summaryLoading}
					<div class="mt-1 h-6 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
				{:else}
					<div class="mt-1 truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white">
						{fmtInt(displayTokens)}
					</div>
				{/if}
			</div>
		</div>

		<div class="h-[72px] flex items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850">
			<div class="h-full w-[3px] shrink-0 bg-[#F4845F]"></div>
			<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
				<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">ESTIMATED COST</div>
				{#if summaryLoading}
					<div class="mt-1 h-6 w-20 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
				{:else}
					<div class="mt-1 truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white">
						{fmtUsdMoney(displayCost)}
					</div>
				{/if}
			</div>
		</div>

		<div class="h-[72px] flex items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850">
			<div class="h-full w-[3px] shrink-0 bg-[#9B59B6]"></div>
			<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
				<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">AVG TOKENS / MSG</div>
				{#if summaryLoading}
					<div class="mt-1 h-6 w-14 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
				{:else}
					<div class="mt-1 truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white">
						{displayAvg.toFixed(1)}
					</div>
				{/if}
			</div>
		</div>

		<div class="h-[72px] flex items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850">
			<div class="h-full w-[3px] shrink-0 bg-[#3B82F6]"></div>
			<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
				<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">TODAY'S TOKENS</div>
				<div class="mt-1 flex min-w-0 items-center gap-2">
					{#if dailyLoading}
						<div class="h-6 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
					{:else}
						<div class="truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white">
							{daily ? fmtInt(daily.today_tokens) : '—'}
						</div>
					{/if}
					{#if !dailyLoading && daily && daily.yesterday_tokens !== 0 && daily.change_percent !== null}
						{#if daily.change_percent > 0}
							<span class="inline-flex shrink-0 rounded-full bg-[#dcfce7] px-[6px] py-[1px] text-[10px] font-bold text-[#16a34a]">
								▲ +{daily.change_percent}%
							</span>
						{:else if daily.change_percent < 0}
							<span class="inline-flex shrink-0 rounded-full bg-[#fee2e2] px-[6px] py-[1px] text-[10px] font-bold text-[#dc2626]">
								▼ {Math.abs(daily.change_percent)}%
							</span>
						{/if}
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Shared chart + table card: side by side on lg+ -->
	<div
		class="mb-6 overflow-hidden rounded-[12px] border border-[#eeeeee] bg-white shadow-[0_1px_6px_rgba(0,0,0,0.06)] dark:border-gray-700 dark:bg-gray-850"
	>
		<div class="flex flex-col lg:flex-row lg:divide-x lg:divide-[#f0f0f0] dark:lg:divide-gray-700">
			<!-- LEFT: Model Usage Overview -->
			<div class="flex min-h-0 min-w-0 flex-1 flex-col p-5 lg:w-1/2 lg:p-6">
				<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
					<h2 class="text-[18px] font-bold leading-tight text-gray-900 dark:text-white">
						{$i18n.t('Model Usage Overview')}
					</h2>
					<div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
						<div class="relative min-w-[140px]" data-bar-calendar-root>
							<select
								class="filter-dd w-full cursor-pointer appearance-none pr-8"
								bind:value={barPreset}
								on:change={async () => {
									if (barPreset === 'custom') {
										showBarCalendar = true;
										if (!barCustomStart) barCustomStart = dayjs.utc().subtract(29, 'day').format('YYYY-MM-DD');
										if (!barCustomEnd) barCustomEnd = dayjs.utc().format('YYYY-MM-DD');
									} else {
										showBarCalendar = false;
										await loadBars();
									}
								}}
							>
								<option value="7">{$i18n.t('Last 7 Days')}</option>
								<option value="20">{$i18n.t('Last 20 Days')}</option>
								<option value="30">{$i18n.t('Last 30 Days')}</option>
								<option value="all">{$i18n.t('All Time')}</option>
								<option value="custom">{$i18n.t('Custom Range')}</option>
							</select>
							{#if showBarCalendar && barPreset === 'custom'}
								<div
									class="absolute right-0 z-50 mt-2 w-[280px] rounded-xl border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-600 dark:bg-gray-800"
								>
									<p class="mb-2 text-xs text-gray-500">{$i18n.t('Start date')}</p>
									<input type="date" class="filter-dd mb-3 w-full" bind:value={barCustomStart} />
									<p class="mb-2 text-xs text-gray-500">{$i18n.t('End date')}</p>
									<input type="date" class="filter-dd mb-4 w-full" bind:value={barCustomEnd} />
									<div class="flex justify-end gap-2">
										<button
											type="button"
											class="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
											on:click={() => {
												showBarCalendar = false;
											}}>{$i18n.t('Cancel')}</button
										>
										<button
											type="button"
											class="rounded-lg bg-black px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-40 dark:bg-white dark:text-black"
											disabled={!barCustomStart ||
												!barCustomEnd ||
												barCustomEnd < barCustomStart}
											on:click={applyCustomBarRange}
										>
											{$i18n.t('Apply')}
										</button>
									</div>
								</div>
							{/if}
						</div>
						<button
							type="button"
							class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#e0e0e0] text-gray-600 transition hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
							aria-label={$i18n.t('Expand')}
							on:click={() => {
								showBarCalendar = false;
								showChartModal = true;
							}}
						>
							<ArrowsPointingOut className="h-5 w-5" strokeWidth="1.75" />
						</button>
					</div>
				</div>

				{#if barsError}
					<div class="flex flex-col items-center justify-center gap-2 py-12" style="min-height: {CHART_HEIGHT}px">
						<p class="text-center text-red-600 dark:text-red-400">{$i18n.t('Failed to load data.')}</p>
						<button
							type="button"
							class="rounded-lg border border-[#e0e0e0] px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
							on:click={loadBars}
						>
							{$i18n.t('Retry')}
						</button>
					</div>
				{:else if barsLoading}
					<div class="w-full" style="height: {CHART_HEIGHT}px">
						<div class="flex h-full items-end gap-6 px-1">
							{#each [1, 2, 3, 4, 5, 6] as _}
								<div class="flex min-w-0 flex-1 items-end justify-center">
									<div class="flex max-w-[72px] items-end gap-0">
										<div class="h-24 w-1/2 min-w-[14px] animate-pulse rounded-tl-[6px] bg-gray-200 dark:bg-gray-700"></div>
										<div class="h-20 w-1/2 min-w-[14px] animate-pulse rounded-tr-[6px] bg-gray-100 dark:bg-gray-800"></div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{:else if usageRowsTop.length === 0}
					<p class="py-16 text-center text-gray-500">{$i18n.t('No usage data for this period')}</p>
				{:else}
					<div class="relative min-w-0">
						<div class="relative w-full" style="height: {CHART_HEIGHT}px">
							{#each usageYAxisTicks as tick, idx}
								<div
									class="absolute inset-x-0 border-t border-dashed border-[#f0f0f0] dark:border-gray-700/40"
									style="top: {(idx / (usageYAxisTicks.length - 1)) * 100}%"
								></div>
							{/each}
							<div class="absolute inset-y-0 left-0 w-11 shrink-0">
								{#each usageYAxisTicks as tick, idx}
									<div
										class="absolute -translate-y-1/2 text-[11px] text-[#999] dark:text-gray-400"
										style="top: {(idx / (usageYAxisTicks.length - 1)) * 100}%"
									>
										{fmtAxisToken(tick)}
									</div>
								{/each}
							</div>
							<div class="absolute inset-y-0 left-11 right-0 min-w-0 overflow-hidden">
								<div class="flex h-full items-end gap-6 px-0.5 pb-7">
									{#each modelUsageRows as row (row.model_id + '-' + barTickKey)}
										{@const isHover = hoverGroupId === row.model_id}
										{@const tHeight = barHeightPx(row.tokens, usageYAxisMax, CHART_HEIGHT)}
										{@const pHeight = barHeightPx(row.price, usageYAxisMax, CHART_HEIGHT)}
										<div
											class="flex h-full min-w-0 flex-1 flex-col items-stretch justify-end"
											on:mouseenter={() => (hoverGroupId = row.model_id)}
											on:mouseleave={() => (hoverGroupId = null)}
										>
											<div class="relative flex min-h-0 flex-1 flex-col items-center justify-end">
												{#if isHover}
													<div
														class="absolute bottom-full z-20 mb-1 w-[min(200px,calc(100vw-2rem))] rounded-[8px] border border-[#ececec] bg-white px-[14px] py-[10px] text-left text-[12px] shadow-[0_4px_12px_rgba(0,0,0,0.12)] dark:border-gray-700 dark:bg-gray-900"
													>
														<div class="truncate font-semibold text-[#111] dark:text-white">{row.model_name}</div>
														<div class="mt-1 text-gray-600 dark:text-gray-300">Tokens: {fmtInt(row.tokens)}</div>
														<div class="text-gray-600 dark:text-gray-300">Cost: {fmtUsd3(row.price)}</div>
													</div>
												{/if}
												<div class="flex w-full max-w-[72px] items-end justify-center gap-0">
													<div
														class="usage-bar-grow min-h-[4px] w-1/2 min-w-[14px] rounded-tl-[6px] rounded-tr-none transition-all duration-300 ease-out"
														style="height: {tHeight}px; background: linear-gradient(180deg, #4ade80 0%, rgba(74, 222, 128, 0.15) 100%); opacity: {isHover ? 1 : 0.82};"
													></div>
													<div
														class="usage-bar-grow min-h-[4px] w-1/2 min-w-[14px] rounded-tr-[6px] rounded-tl-none transition-all duration-300 ease-out"
														style="height: {pHeight}px; background: linear-gradient(180deg, #fbbf24 0%, rgba(251, 191, 36, 0.15) 100%); opacity: {isHover ? 1 : 0.82};"
													></div>
												</div>
												<div
													class="mt-2 w-full truncate text-center text-[11px] leading-tight text-[#999] dark:text-gray-400"
													title={row.model_name}
												>
													{shortModelName(row.model_name)}
												</div>
											</div>
										</div>
									{/each}
								</div>
							</div>
						</div>
						<div class="mt-3 flex flex-wrap items-center justify-center gap-4 text-[12px] text-[#666] dark:text-gray-400 sm:gap-5">
							<div class="inline-flex items-center gap-2">
								<span class="h-2 w-2 shrink-0 rounded-full bg-[#4ade80]"></span>
								{$i18n.t('Tokens')}
							</div>
							<div class="inline-flex items-center gap-2">
								<span class="h-2 w-2 shrink-0 rounded-full bg-[#fbbf24]"></span>
								{$i18n.t('Price')}
							</div>
						</div>
					</div>
				{/if}
			</div>

			<!-- RIGHT: Token Breakdown -->
			<div class="flex min-h-0 min-w-0 flex-1 flex-col border-t border-[#f0f0f0] p-5 pt-6 dark:border-gray-700 lg:w-1/2 lg:border-t-0 lg:p-6">
				<div class="mb-4 flex flex-wrap items-start justify-between gap-3">
					<h2 class="text-[18px] font-bold leading-tight text-gray-900 dark:text-white">
						{$i18n.t('Token Breakdown')}
					</h2>
					<select class="filter-dd min-w-[160px] shrink-0" bind:value={tableUserId} on:change={loadBreakdown}>
						<option value="">{$i18n.t('All Users')}</option>
						{#each adminUsers as u}
							<option value={u.id}>{u.name || u.email || u.id}</option>
						{/each}
					</select>
				</div>
				{#if tableError && breakdownRows.length === 0}
					<div class="mb-3 flex items-center gap-3 text-red-600 dark:text-red-400">
						<span>{tableError}</span>
						<button type="button" class="text-sm underline" on:click={loadBreakdown}>{$i18n.t('Retry')}</button>
					</div>
				{/if}
				<div
					class={breakdownTableScroll ? 'token-table-scroll max-h-[280px] overflow-y-auto pr-0.5' : ''}
				>
					<table class="w-full table-fixed border-collapse text-sm">
						<colgroup>
							<col style="width: 34px" />
							<col />
							<col style="width: 90px" />
							<col style="width: 84px" />
							<col style="width: 84px" />
						</colgroup>
						<thead>
							<tr class="border-b border-[#e8e8e8] dark:border-gray-700">
								<th
									class="py-2 pr-2 text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-[#999] {breakdownTableScroll
										? 'sticky top-0 z-10 bg-white shadow-sm dark:bg-gray-850'
										: ''}">#</th
								>
								<th
									class="py-2 pr-2 text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-[#999] {breakdownTableScroll
										? 'sticky top-0 z-10 bg-white shadow-sm dark:bg-gray-850'
										: ''}">{$i18n.t('Model')}</th
								>
								<th
									class="py-2 pr-2 text-right text-[11px] font-semibold uppercase tracking-[0.02em] text-[#999] {breakdownTableScroll
										? 'sticky top-0 z-10 bg-white shadow-sm dark:bg-gray-850'
										: ''}">{$i18n.t('Total Tokens')}</th
								>
								<th
									class="py-2 pr-2 text-right text-[11px] font-semibold uppercase tracking-[0.02em] text-[#999] {breakdownTableScroll
										? 'sticky top-0 z-10 bg-white shadow-sm dark:bg-gray-850'
										: ''}">{$i18n.t('Price/1M')}</th
								>
								<th
									class="py-2 text-right text-[11px] font-semibold uppercase tracking-[0.02em] text-[#999] {breakdownTableScroll
										? 'sticky top-0 z-10 bg-white shadow-sm dark:bg-gray-850'
										: ''}">{$i18n.t('Total Cost')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#if tableLoading}
								{#each [1, 2, 3, 4, 5] as _}
									<tr class="border-b border-[#f5f5f5] dark:border-gray-800">
										<td colspan="5" class="py-2">
											<div class="h-5 animate-pulse rounded bg-gray-100 dark:bg-gray-800"></div>
										</td>
									</tr>
								{/each}
							{:else if sortedBreakdown.length === 0}
								<tr>
									<td colspan="5" class="py-8 text-center text-gray-500">{$i18n.t('No token data available')}</td>
								</tr>
							{:else}
								{#each sortedBreakdown as row, i}
									<tr class="border-b border-[#f5f5f5] text-[13px] hover:bg-[#f9f9f9] dark:border-gray-800 dark:hover:bg-gray-800/80">
										<td class="py-2 pr-2 text-left tabular-nums text-gray-600 dark:text-gray-300">{i + 1}</td>
										<td class="truncate py-2 pr-2 text-left text-[#111] dark:text-white" title={row.model_name}
											>{row.model_name}</td
										>
										<td class="py-2 pr-2 text-right tabular-nums text-[#111] dark:text-white"
											>{fmtInt(row.total_tokens)}</td
										>
										<td class="py-2 pr-2 text-right tabular-nums text-[#111] dark:text-white">
											{#if row.price_per_1k_usd != null}{fmtUsd4(row.price_per_1k_usd)}{:else}<span class="text-gray-400">—</span
												>{/if}
										</td>
										<td class="py-2 text-right tabular-nums text-[#111] dark:text-white">
											{#if row.total_cost_usd != null}{fmtUsd3(row.total_cost_usd)}{:else}<span class="text-gray-400">—</span
												>{/if}
										</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			</div>
		</div>
	</div>

	{#if showChartModal}
		<div
			class="fixed inset-0 z-[200] flex items-center justify-center p-3 sm:p-6"
			role="dialog"
			aria-modal="true"
			aria-labelledby="chart-modal-title"
		>
			<button
				type="button"
				class="absolute inset-0 bg-black/60 backdrop-blur-[1px]"
				aria-label={$i18n.t('Close')}
				on:click={() => (showChartModal = false)}
			></button>
			<div
				class="relative z-10 flex min-h-0 max-h-[92vh] w-full max-w-[min(1400px,96vw)] flex-col overflow-hidden rounded-2xl border border-[#e8e8e8] bg-white shadow-2xl dark:border-gray-600 dark:bg-gray-850"
			>
				<div
					class="flex flex-wrap items-center justify-between gap-3 border-b border-[#efefef] px-4 py-3 dark:border-gray-700"
				>
					<h2 id="chart-modal-title" class="text-lg font-bold text-gray-900 dark:text-white">
						{$i18n.t('Model Usage Overview')}
					</h2>
					<div class="flex flex-wrap items-center justify-end gap-2">
						<div class="relative min-w-[160px]" data-bar-calendar-root-modal>
							<select
								class="filter-dd w-full cursor-pointer appearance-none pr-8"
								bind:value={barPreset}
								on:change={async () => {
									if (barPreset === 'custom') {
										showBarCalendar = true;
										if (!barCustomStart) barCustomStart = dayjs.utc().subtract(29, 'day').format('YYYY-MM-DD');
										if (!barCustomEnd) barCustomEnd = dayjs.utc().format('YYYY-MM-DD');
									} else {
										showBarCalendar = false;
										await loadBars();
									}
								}}
							>
								<option value="7">{$i18n.t('Last 7 Days')}</option>
								<option value="20">{$i18n.t('Last 20 Days')}</option>
								<option value="30">{$i18n.t('Last 30 Days')}</option>
								<option value="all">{$i18n.t('All Time')}</option>
								<option value="custom">{$i18n.t('Custom Range')}</option>
							</select>
							{#if showBarCalendar && barPreset === 'custom'}
								<div
									class="absolute right-0 z-[250] mt-2 w-[280px] rounded-xl border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-600 dark:bg-gray-800"
								>
									<p class="mb-2 text-xs text-gray-500">{$i18n.t('Start date')}</p>
									<input type="date" class="filter-dd mb-3 w-full" bind:value={barCustomStart} />
									<p class="mb-2 text-xs text-gray-500">{$i18n.t('End date')}</p>
									<input type="date" class="filter-dd mb-4 w-full" bind:value={barCustomEnd} />
									<div class="flex justify-end gap-2">
										<button
											type="button"
											class="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
											on:click={() => {
												showBarCalendar = false;
											}}>{$i18n.t('Cancel')}</button
										>
										<button
											type="button"
											class="rounded-lg bg-black px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-40 dark:bg-white dark:text-black"
											disabled={!barCustomStart ||
												!barCustomEnd ||
												barCustomEnd < barCustomStart}
											on:click={applyCustomBarRange}
										>
											{$i18n.t('Apply')}
										</button>
									</div>
								</div>
							{/if}
						</div>
						<button
							type="button"
							class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#e0e0e0] text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
							aria-label={$i18n.t('Close')}
							on:click={() => (showChartModal = false)}
						>
							<XMark className="h-5 w-5" strokeWidth="1.75" />
						</button>
					</div>
				</div>

				<div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto p-8">
					{#if barsError}
						<div class="flex min-h-[240px] flex-col items-center justify-center gap-2 py-12">
							<p class="text-center text-red-600 dark:text-red-400">{$i18n.t('Failed to load data.')}</p>
							<button
								type="button"
								class="rounded-lg border border-[#e0e0e0] px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
								on:click={loadBars}
							>
								{$i18n.t('Retry')}
							</button>
						</div>
					{:else if barsLoading}
						<div class="flex w-full items-end justify-evenly gap-12 px-2" style="min-height: {CHART_HEIGHT_MODAL}px">
							{#each [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as _}
								<div class="flex max-w-[88px] flex-1 flex-col items-center justify-end gap-0 pb-10">
									<div class="flex w-full items-end gap-0">
										<div class="h-36 w-1/2 min-w-[20px] animate-pulse rounded-tl-md bg-gray-200 dark:bg-gray-700"></div>
										<div class="h-28 w-1/2 min-w-[20px] animate-pulse rounded-tr-md bg-gray-100 dark:bg-gray-800"></div>
									</div>
								</div>
							{/each}
						</div>
					{:else if modelUsageRowsAll.length === 0}
						<p class="py-24 text-center text-gray-500">{$i18n.t('No usage data for this period')}</p>
					{:else}
						<div class="flex w-full flex-1 flex-col items-stretch justify-center">
							<div class="relative mx-auto w-full max-w-full" style="height: {CHART_HEIGHT_MODAL}px">
								{#each modalYAxisTicks as tick, idx}
									<div
										class="absolute inset-x-0 border-t border-dashed border-[#f0f0f0] dark:border-gray-700/40"
										style="top: {(idx / (modalYAxisTicks.length - 1)) * 100}%"
									></div>
								{/each}
								<div class="absolute inset-y-0 left-0 w-12 shrink-0">
									{#each modalYAxisTicks as tick, idx}
										<div
											class="absolute -translate-y-1/2 text-[11px] text-[#999] dark:text-gray-400"
											style="top: {(idx / (modalYAxisTicks.length - 1)) * 100}%"
										>
											{fmtAxisToken(tick)}
										</div>
									{/each}
								</div>
								<div class="absolute inset-y-0 left-12 right-0 overflow-x-auto overflow-y-hidden">
									<div
										class="flex h-full min-w-full items-end justify-evenly gap-12 pb-10"
										style="min-width: max(100%, {Math.max(modelUsageRowsAll.length * 96, 400)}px)"
									>
										{#each modelUsageRowsAll as row (row.model_id + '-modal-' + barTickKey)}
											{@const isHoverM = hoverGroupIdModal === row.model_id}
											{@const tHeightM = barHeightPx(row.tokens, modalYAxisMax, CHART_HEIGHT_MODAL)}
											{@const pHeightM = barHeightPx(row.price, modalYAxisMax, CHART_HEIGHT_MODAL)}
											<div
												class="flex h-full w-[104px] shrink-0 flex-col items-center justify-end"
												on:mouseenter={() => (hoverGroupIdModal = row.model_id)}
												on:mouseleave={() => (hoverGroupIdModal = null)}
											>
												<div class="relative flex w-full flex-col items-center justify-end">
													{#if isHoverM}
														<div
															class="absolute bottom-full z-20 mb-1 w-[200px] rounded-lg border border-[#ececec] bg-white px-3 py-2 text-left text-[12px] shadow-lg dark:border-gray-700 dark:bg-gray-900"
														>
															<div class="font-semibold text-[#111] dark:text-white">{row.model_name}</div>
															<div class="mt-1 text-gray-600 dark:text-gray-300">Tokens: {fmtInt(row.tokens)}</div>
															<div class="text-gray-600 dark:text-gray-300">Cost: {fmtUsd3(row.price)}</div>
														</div>
													{/if}
													<div class="flex w-full items-end justify-center gap-0">
														<div
															class="usage-bar-grow min-h-[4px] w-[44px] shrink-0 rounded-tl-md rounded-tr-none transition-all duration-300 ease-out"
															style="height: {tHeightM}px; background: linear-gradient(180deg, #4ade80 0%, rgba(74, 222, 128, 0.15) 100%); opacity: {isHoverM ? 1 : 0.82};"
														></div>
														<div
															class="usage-bar-grow min-h-[4px] w-[44px] shrink-0 rounded-tr-md rounded-tl-none transition-all duration-300 ease-out"
															style="height: {pHeightM}px; background: linear-gradient(180deg, #fbbf24 0%, rgba(251, 191, 36, 0.15) 100%); opacity: {isHoverM ? 1 : 0.82};"
														></div>
													</div>
													<div
														class="mt-2 line-clamp-2 max-h-10 w-full px-0.5 text-center text-[11px] leading-tight text-[#666] dark:text-gray-400"
														title={row.model_name}
													>
														{row.model_name}
													</div>
												</div>
											</div>
										{/each}
									</div>
								</div>
							</div>
						</div>
					{/if}
				</div>

				<div
					class="flex shrink-0 flex-wrap items-center justify-center gap-6 border-t border-[#efefef] px-4 py-3 text-[13px] text-[#666] dark:border-gray-700 dark:text-gray-400"
				>
					<div class="inline-flex items-center gap-2">
						<span class="h-2 w-2 rounded-full bg-[#4ade80]"></span>
						{$i18n.t('Tokens')}
					</div>
					<div class="inline-flex items-center gap-2">
						<span class="h-2 w-2 rounded-full bg-[#fbbf24]"></span>
						{$i18n.t('Price')}
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.filter-dd {
		@apply rounded-lg border border-[#e0e0e0] bg-white px-[14px] py-2 text-[14px] text-gray-900 outline-none dark:border-gray-700 dark:bg-gray-850 dark:text-white;
	}

	.usage-bar-grow {
		transform-origin: bottom;
		animation: usageBarGrow 300ms ease-out;
	}

	@keyframes usageBarGrow {
		from {
			transform: scaleY(0);
		}
		to {
			transform: scaleY(1);
		}
	}

	.token-table-scroll::-webkit-scrollbar {
		width: 6px;
	}

	.token-table-scroll::-webkit-scrollbar-track {
		background: #e0e0e0;
		border-radius: 999px;
	}

	.token-table-scroll::-webkit-scrollbar-thumb {
		background: #c0c0c0;
		border-radius: 999px;
	}
</style>
