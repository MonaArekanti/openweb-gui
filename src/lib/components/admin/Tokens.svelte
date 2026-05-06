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

	dayjs.extend(utc);

	const i18n = getContext('i18n');

	type BarPreset = '7' | '20' | '30' | 'all' | 'custom';

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
	let barMetric: 'tokens' | 'price' = 'tokens';
	let barCustomStart = '';
	let barCustomEnd = '';
	let showBarCalendar = false;

	let barRows: ModelBarRow[] = [];
	let barsLoading = true;
	let barsError: string | null = null;
	let barTickKey = 0;

	let tableUserId = '';
	let breakdownRows: BreakdownRow[] = [];
	let tableLoading = true;
	let tableError: string | null = null;

	let adminUsers: { id: string; name: string; email?: string }[] = [];

	let expandOpen = false;

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

	function fmtAxisVal(n: number, metric: 'tokens' | 'price') {
		if (metric === 'tokens') {
			if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
			if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
			return String(Math.round(n));
		}
		return '$' + n.toFixed(2);
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
			barRows = await getModelTokenBars(localStorage.token, {
				start_date: r.start,
				end_date: r.end,
				metric: barMetric
			});
			barTickKey += 1;
		} catch (e: unknown) {
			barsError = typeof e === 'object' && e && 'detail' in e ? String((e as { detail: unknown }).detail) : 'Failed to load';
			barRows = [];
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
		const va = Number(a[sortKey]);
		const vb = Number(b[sortKey]);
		return mul * (va - vb);
	}

	$: sortedBreakdown = [...breakdownRows].sort(cmpRows);

	function handleWindowClick(e: MouseEvent) {
		const t = e.target;
		const el = t instanceof Element ? t : (t as Node).parentElement;
		if (!el) return;
		if (showBarCalendar && !el.closest('[data-bar-calendar-root]')) showBarCalendar = false;
	}

	function handleExpandEscape(e: KeyboardEvent) {
		if (e.key !== 'Escape') return;
		if (expandOpen) expandOpen = false;
	}

	function applyCustomBarRange() {
		if (!barCustomStart || !barCustomEnd || barCustomEnd < barCustomStart) return;
		showBarCalendar = false;
		barPreset = 'custom';
		loadBars();
	}

	$: maxBarVal = Math.max(1e-9, ...barRows.map((r) => r.value));
	$: axisTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxBarVal);

	onMount(async () => {
		window.addEventListener('click', handleWindowClick);
		try {
			adminUsers = (await getUsers(localStorage.token)) ?? [];
		} catch {
			adminUsers = [];
		}
		await loadSummaryBlock();
		await Promise.all([loadBars(), loadBreakdown()]);
		return () => {
			window.removeEventListener('click', handleWindowClick);
			cancelCountUp();
		};
	});
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleExpandEscape} />

<div class="tokens-admin pb-12 bg-[#f9f9f9] dark:bg-gray-900 min-h-full -mx-[16px] px-4 md:px-6 pt-2">
	<h1 class="text-[28px] font-bold text-gray-900 dark:text-white mb-10">
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

	<!-- Top stats row: 3 bubbles + daily card -->
	<div
		class="flex flex-wrap justify-center items-center gap-x-[60px] gap-y-8 mb-12 px-1"
		aria-live="polite"
	>
		<!-- Teal -->
		<div class="flex flex-col items-center shrink-0">
			<div
				class="relative flex h-[180px] w-[180px] shrink-0 items-center justify-center rounded-full text-white shadow-[0_8px_32px_rgba(0,0,0,0.18)]"
				style="background: radial-gradient(circle at 35% 35%, #5ee8dc, #2EC4B6 45%, #0e6e67);"
			>
				{#if summaryLoading}
					<div class="h-12 w-28 animate-pulse rounded bg-white/25"></div>
				{:else}
					<span class="text-[42px] font-bold leading-none tabular-nums">{fmtInt(displayTokens)}</span>
				{/if}
			</div>
			<p class="mt-3 text-[13px] text-gray-500 dark:text-gray-400 text-center max-w-[11rem]">
				{$i18n.t('Total Tokens Used')}
			</p>
		</div>

		<!-- Orange -->
		<div class="flex flex-col items-center shrink-0">
			<div
				class="relative flex h-[180px] w-[180px] shrink-0 items-center justify-center rounded-full text-white shadow-[0_8px_32px_rgba(0,0,0,0.18)]"
				style="background: radial-gradient(circle at 35% 35%, #f5b394, #E8845A 45%, #b5471e);"
			>
				{#if summaryLoading}
					<div class="h-12 w-28 animate-pulse rounded bg-white/25"></div>
				{:else}
					<span class="text-[42px] font-bold leading-none tabular-nums">{fmtUsdMoney(displayCost)}</span>
				{/if}
			</div>
			<p class="mt-3 text-[13px] text-gray-500 dark:text-gray-400 text-center max-w-[11rem]">
				{$i18n.t('Total Estimated Cost')}
			</p>
		</div>

		<!-- Purple -->
		<div class="flex flex-col items-center shrink-0">
			<div
				class="relative flex h-[180px] w-[180px] shrink-0 items-center justify-center rounded-full text-white shadow-[0_8px_32px_rgba(0,0,0,0.18)]"
				style="background: radial-gradient(circle at 35% 35%, #c9a6f5, #9B59B6 45%, #6a1f9a);"
			>
				{#if summaryLoading}
					<div class="h-12 w-24 animate-pulse rounded bg-white/25"></div>
				{:else}
					<span class="text-[42px] font-bold leading-none tabular-nums">{displayAvg.toFixed(1)}</span>
				{/if}
			</div>
			<p class="mt-3 text-[13px] text-gray-500 dark:text-gray-400 text-center max-w-[13rem]">
				{$i18n.t('Average Tokens per Message')}
			</p>
		</div>

		<!-- Daily card -->
		<div
			class="w-full max-w-[280px] lg:w-[220px] lg:max-w-none min-h-[180px] flex flex-col justify-center rounded-2xl border border-[#e8e8e8] bg-white px-6 py-5 shadow-[0_4px_16px_rgba(0,0,0,0.08)] dark:border-gray-700 dark:bg-gray-850"
		>
			<p class="text-[13px] font-bold uppercase tracking-wide text-[#888] dark:text-gray-400 mb-4">
				{$i18n.t('Daily Tokens')}
			</p>
			{#if dailyLoading}
				<div class="space-y-3 animate-pulse">
					<div class="h-4 w-24 rounded bg-gray-200 dark:bg-gray-700"></div>
					<div class="h-8 w-32 rounded bg-gray-200 dark:bg-gray-700"></div>
					<div class="h-4 w-24 rounded bg-gray-200 dark:bg-gray-700"></div>
					<div class="h-8 w-28 rounded bg-gray-200 dark:bg-gray-700"></div>
				</div>
			{:else if daily}
				<div class="space-y-1">
					<p class="text-[12px] text-gray-500 dark:text-gray-400">{$i18n.t('Total Tokens')}</p>
					<p class="text-[22px] font-bold text-[#111] dark:text-white tabular-nums">
						{fmtInt(daily.today_tokens)}
					</p>
				</div>
				<div class="mt-4 space-y-1">
					<p class="text-[12px] text-gray-500 dark:text-gray-400">{$i18n.t('Total Cost')}</p>
					<p class="text-[22px] font-bold text-[#111] dark:text-white tabular-nums">
						{fmtUsd3(daily.today_cost_usd)}
					</p>
				</div>
				<div class="my-4 border-t border-[#f0f0f0] dark:border-gray-700"></div>
				<div class="text-[12px]">
					{#if daily.yesterday_tokens === 0}
						<span class="text-[#888]">{$i18n.t('No data yesterday')}</span>
					{:else if daily.change_percent === null}
						<span class="text-[#888]">—</span>
					{:else if daily.change_percent > 0}
						<span class="text-[#16a34a]">▲ +{daily.change_percent}% {$i18n.t('from yesterday')}</span>
					{:else if daily.change_percent < 0}
						<span class="text-[#dc2626]"
							>▼ {Math.abs(daily.change_percent)}% {$i18n.t('from yesterday')}</span
						>
					{:else}
						<span class="text-[#888]">→ 0% {$i18n.t('from yesterday')}</span>
					{/if}
				</div>
			{/if}
		</div>
	</div>

	<!-- Model usage bar chart card -->
	<div
		class="rounded-xl border border-[#efefef] dark:border-gray-700 bg-white dark:bg-gray-850 shadow-[0_1px_4px_rgba(0,0,0,0.08)] mb-10 overflow-hidden"
	>
		<div class="flex flex-col gap-4 border-b border-[#efefef] dark:border-gray-700 px-6 py-5 md:flex-row md:items-center md:justify-between">
			<h2 class="text-[18px] font-bold text-gray-900 dark:text-white">
				{$i18n.t('Model Usage Overview')}
			</h2>
			<div class="flex flex-wrap items-center gap-3">
				<div class="relative min-w-[160px]" data-bar-calendar-root>
					<select
						class="filter-dd w-full flex justify-between appearance-none cursor-pointer pr-8"
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

				<select
					class="filter-dd min-w-[120px]"
					bind:value={barMetric}
					on:change={loadBars}
				>
					<option value="tokens">{$i18n.t('Tokens')}</option>
					<option value="price">{$i18n.t('Price')}</option>
				</select>
			</div>
		</div>

		<div class="px-6 py-6 overflow-x-auto">
			{#if barsError}
				<p class="text-center text-red-600 dark:text-red-400">{barsError}</p>
			{:else if barsLoading}
				<div class="space-y-4 py-2">
					{#each [1, 2, 3, 4, 5] as _}
						<div class="flex items-center gap-3">
							<div class="h-4 w-[180px] shrink-0 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
							<div class="h-8 flex-1 animate-pulse rounded bg-gray-100 dark:bg-gray-800"></div>
						</div>
					{/each}
				</div>
			{:else if barRows.length === 0}
				<p class="py-8 text-center text-gray-500">{$i18n.t('No usage data for this period')}</p>
			{:else}
				<div class="min-w-[640px]">
					{#each barRows as row (row.model_id + '-' + barTickKey)}
						{@const pct = (row.value / maxBarVal) * 100}
						{@const wideEnough = pct > 14}
						<div class="flex items-center gap-3 mb-3">
							<div
								class="w-[200px] shrink-0 truncate text-[13px] text-gray-500 dark:text-gray-400"
								title={row.model_name}
							>
								{row.model_name}
							</div>
							<div class="flex-1 min-w-0 flex items-center gap-2">
								<div class="relative h-8 flex-1 bg-gray-100 dark:bg-gray-800 rounded-r-md overflow-hidden">
									<div
										class="absolute left-0 top-0 h-full rounded-r-md flex items-center justify-end min-w-0 transition-[width] duration-700 ease-out"
										style="width: {pct}%; background: linear-gradient(90deg, #4ade80, #22c55e);"
									>
										{#if wideEnough}
											<span class="relative z-10 pr-2 text-[13px] font-bold text-white tabular-nums">
												{barMetric === 'tokens'
													? fmtInt(row.value)
													: fmtUsd3(row.value)}
											</span>
										{/if}
									</div>
								</div>
								{#if !wideEnough}
									<span class="text-[13px] font-bold text-gray-900 dark:text-white tabular-nums shrink-0">
										{barMetric === 'tokens' ? fmtInt(row.value) : fmtUsd3(row.value)}
									</span>
								{/if}
							</div>
						</div>
					{/each}

					<!-- X-axis -->
					<div class="flex mt-6 pt-2 border-t border-[#f0f0f0] dark:border-gray-700">
						<div class="w-[200px] shrink-0"></div>
						<div class="flex-1 flex justify-between text-[12px] text-gray-400 px-0">
							{#each axisTicks as tick}
								<span class="tabular-nums">{fmtAxisVal(tick, barMetric)}</span>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>
	</div>

	<!-- Token breakdown -->
	<div class="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
		<h2 class="text-[18px] font-bold text-gray-900 dark:text-white">{$i18n.t('Token Breakdown')}</h2>
		<div class="flex flex-wrap items-center gap-3">
			<select
				class="filter-dd min-w-[160px]"
				bind:value={tableUserId}
				on:change={loadBreakdown}
			>
				<option value="">{$i18n.t('All Users')}</option>
				{#each adminUsers as u}
					<option value={u.id}>{u.name || u.email || u.id}</option>
				{/each}
			</select>
			<button
				type="button"
				class="filter-dd bg-white dark:bg-gray-850 hover:bg-gray-50 dark:hover:bg-gray-800"
				on:click={() => (expandOpen = true)}
			>
				{$i18n.t('Expand')}
			</button>
		</div>
	</div>

	{#if tableError && breakdownRows.length === 0}
		<div class="mb-4 text-red-600 dark:text-red-400 flex items-center gap-3">
			<span>{tableError}</span>
			<button type="button" class="underline text-sm" on:click={loadBreakdown}>{$i18n.t('Retry')}</button>
		</div>
	{/if}

	<div
		class="rounded-xl border border-[#e8e8e8] dark:border-gray-700 overflow-hidden bg-white dark:bg-gray-850 shadow-[0_1px_4px_rgba(0,0,0,0.06)]"
	>
		<div class="overflow-x-auto">
			<div class="max-h-[280px] overflow-y-auto">
				<table class="w-full min-w-[720px] border-collapse text-sm">
					<thead class="sticky top-0 z-[1] border-b border-[#e8e8e8] bg-[#fafafa] dark:bg-gray-800 dark:border-gray-700">
						<tr>
							<th class="px-4 py-3 text-left font-bold text-gray-700 dark:text-gray-200 w-10">#</th>
							<th class="px-4 py-3 text-left">
								<button type="button" class="font-bold text-gray-700 dark:text-gray-200 hover:underline" on:click={() => toggleSort('model_name')}>
									{$i18n.t('Model')}
									{sortKey === 'model_name' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
								</button>
							</th>
							<th class="px-4 py-3 text-right">
								<button type="button" class="font-bold text-gray-700 dark:text-gray-200 hover:underline" on:click={() => toggleSort('total_tokens')}>
									{$i18n.t('Total Tokens')}
									{sortKey === 'total_tokens' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
								</button>
							</th>
							<th class="px-4 py-3 text-right">
								<button type="button" class="font-bold text-gray-700 dark:text-gray-200 hover:underline" on:click={() => toggleSort('price_per_1k_usd')}>
									{$i18n.t('Price per 1K tokens')}
									{sortKey === 'price_per_1k_usd' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
								</button>
							</th>
							<th class="px-4 py-3 text-right">
								<button type="button" class="font-bold text-gray-700 dark:text-gray-200 hover:underline" on:click={() => toggleSort('total_cost_usd')}>
									{$i18n.t('Total Cost')}
									{sortKey === 'total_cost_usd' ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
								</button>
							</th>
						</tr>
					</thead>
					<tbody>
						{#if tableLoading}
							{#each [1, 2, 3, 4, 5] as _}
								<tr class="border-b border-[#e8e8e8] dark:border-gray-700">
									<td colspan="5" class="px-4 py-3">
										<div class="h-5 animate-pulse rounded bg-gray-100 dark:bg-gray-800"></div>
									</td>
								</tr>
							{/each}
						{:else if sortedBreakdown.length === 0}
							<tr>
								<td colspan="5" class="px-4 py-10 text-center text-gray-500">
									{$i18n.t('No token data available')}
								</td>
							</tr>
						{:else}
							{#each sortedBreakdown as row, i}
								<tr
									class="border-b border-[#e8e8e8] hover:bg-[#f5f5f5] dark:border-gray-700 dark:hover:bg-gray-800/80"
								>
									<td class="px-4 py-3 text-gray-600 dark:text-gray-300">{i + 1}</td>
									<td class="px-4 py-3 text-gray-900 dark:text-white">{row.model_name}</td>
									<td class="px-4 py-3 text-right tabular-nums">{fmtInt(row.total_tokens)}</td>
									<td class="px-4 py-3 text-right tabular-nums">{fmtUsd3(row.price_per_1k_usd)}</td>
									<td class="px-4 py-3 text-right tabular-nums">{fmtUsd3(row.total_cost_usd)}</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		</div>
	</div>
</div>

{#if expandOpen}
	<div
		class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-4"
		role="dialog"
		aria-modal="true"
		on:click|self={() => (expandOpen = false)}
	>
		<div
			class="relative flex max-h-[92vh] w-full max-w-[1100px] flex-col overflow-hidden rounded-xl bg-white shadow-xl dark:bg-gray-850"
		>
			<div class="flex items-center justify-between border-b border-[#e8e8e8] px-6 py-4 dark:border-gray-700">
				<h3 class="text-lg font-bold text-gray-900 dark:text-white">{$i18n.t('Token Breakdown')}</h3>
				<button
					type="button"
					class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					aria-label={$i18n.t('Close')}
					on:click={() => (expandOpen = false)}
				>
					✕
				</button>
			</div>
			<div class="overflow-auto flex-1 p-6">
				<table class="w-full min-w-[720px] border-collapse text-sm">
					<thead class="sticky top-0 bg-[#fafafa] dark:bg-gray-800">
						<tr class="border-b border-[#e8e8e8] dark:border-gray-700">
							<th class="px-4 py-3 text-left font-bold">#</th>
							<th class="px-4 py-3 text-left font-bold">{$i18n.t('Model')}</th>
							<th class="px-4 py-3 text-right font-bold">{$i18n.t('Total Tokens')}</th>
							<th class="px-4 py-3 text-right font-bold">{$i18n.t('Price per 1K tokens')}</th>
							<th class="px-4 py-3 text-right font-bold">{$i18n.t('Total Cost')}</th>
						</tr>
					</thead>
					<tbody>
						{#each sortedBreakdown as row, i}
							<tr class="border-b border-[#e8e8e8] dark:border-gray-700 hover:bg-[#f5f5f5] dark:hover:bg-gray-800/80">
								<td class="px-4 py-3">{i + 1}</td>
								<td class="px-4 py-3">{row.model_name}</td>
								<td class="px-4 py-3 text-right tabular-nums">{fmtInt(row.total_tokens)}</td>
								<td class="px-4 py-3 text-right tabular-nums">{fmtUsd3(row.price_per_1k_usd)}</td>
								<td class="px-4 py-3 text-right tabular-nums">{fmtUsd3(row.total_cost_usd)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	</div>
{/if}

<style>
	.filter-dd {
		@apply rounded-lg border border-[#e0e0e0] bg-white px-[14px] py-2 text-[14px] text-gray-900 outline-none dark:border-gray-700 dark:bg-gray-850 dark:text-white;
	}
</style>
