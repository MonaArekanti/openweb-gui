<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import dayjs from 'dayjs';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import { fade, scale } from 'svelte/transition';

	import { getModels } from '$lib/apis';
	import { getUsers } from '$lib/apis/users';
	import {
		getAdminChatStats,
		getAdminChats,
		getAdminChatMessages,
		type AdminChatRow,
		type AdminMessageRow
	} from '$lib/apis/admin_chats';

	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	dayjs.extend(localizedFormat);

	const i18n = getContext('i18n');

	const TAG_OPTIONS = [
		'HEALTH',
		'FINANCE',
		'MANUFACTURING',
		'AUTOMOTIVE',
		'ENVIRONMENT',
		'RETAIL',
		'TECH',
		'LOGISTICS',
		'GOVERNMENT'
	] as const;

	type TimePreset = '7' | '20' | '30' | 'all' | 'custom';

	let stats: { total_documents: number; flagged_documents: number } | null = null;
	let statsLoading = true;

	let adminUsers: { id: string; name: string; email?: string }[] = [];
	let modelsList: { id: string; name: string }[] = [];

	let userFilter = '';
	let modelFilter = '';
	let selectedTags: Set<string> = new Set();
	/** Default: no date window so the list shows all chats until the user narrows the range. */
	let timePreset: TimePreset = 'all';
	let customStart = '';
	let customEnd = '';
	let showCalendar = false;
	let tagMenuOpen = false;

	let chats: AdminChatRow[] = [];
	let page = 1;
	let loading = false;
	let loadingMore = false;
	let hasMore = true;
	let listError: string | null = null;

	let sentinel: HTMLDivElement | null = null;

	let modalOpen = false;
	let modalChat: AdminChatRow | null = null;
	let modalMessages: AdminMessageRow[] = [];
	let modalLoading = false;

	function computeDateRange(): { start?: string; end?: string } {
		if (timePreset === 'all') return {};
		if (timePreset === 'custom') {
			if (!customStart || !customEnd) return {};
			return { start: customStart, end: customEnd };
		}
		const days = timePreset === '7' ? 7 : timePreset === '20' ? 20 : 30;
		const end = dayjs();
		const start = end.subtract(days, 'day');
		return {
			start: start.format('YYYY-MM-DD'),
			end: end.format('YYYY-MM-DD')
		};
	}

	function tagQueryParam(): string | undefined {
		if (selectedTags.size === 0) return undefined;
		return [...selectedTags].join(',');
	}

	function statsQueryParams() {
		const r = computeDateRange();
		return {
			user_id: userFilter || undefined,
			model_id: modelFilter || undefined,
			tag: tagQueryParam(),
			start_date: r.start,
			end_date: r.end
		};
	}

	async function loadStats() {
		statsLoading = true;
		try {
			stats = await getAdminChatStats(localStorage.token, statsQueryParams());
		} catch (e) {
			console.error(e);
			stats = { total_documents: 0, flagged_documents: 0 };
		} finally {
			statsLoading = false;
		}
	}

	async function resetAndLoad() {
		page = 1;
		chats = [];
		hasMore = true;
		await loadPage(true);
	}

	async function loadPage(reset = false) {
		if (loading || loadingMore) return;
		const isFirst = reset || page === 1;
		if (isFirst) loading = true;
		else loadingMore = true;
		listError = null;
		try {
			const r = computeDateRange();
			const rows = await getAdminChats(localStorage.token, {
				user_id: userFilter || undefined,
				model_id: modelFilter || undefined,
				tag: tagQueryParam(),
				start_date: r.start,
				end_date: r.end,
				page,
				limit: 20
			});
			if (isFirst) chats = rows;
			else chats = [...chats, ...rows];
			hasMore = rows.length >= 20;
		} catch (e: any) {
			listError = e?.detail ?? String(e);
			if (isFirst) chats = [];
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMore() {
		if (!hasMore || loading || loadingMore) return;
		page += 1;
		await loadPage(false);
	}

	function setupObserver() {
		if (!sentinel || typeof IntersectionObserver === 'undefined') return;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries[0]?.isIntersecting) loadMore();
			},
			{ root: null, rootMargin: '160px', threshold: 0 }
		);
		io.observe(sentinel);
		return () => io.disconnect();
	}

	let cleanupObserver: (() => void) | undefined;

	$: if (sentinel) {
		cleanupObserver?.();
		cleanupObserver = setupObserver();
	}

	async function onFilterChange() {
		page = 1;
		await Promise.all([loadStats(), resetAndLoad()]);
	}

	async function toggleTag(tag: string) {
		const next = new Set(selectedTags);
		if (next.has(tag)) next.delete(tag);
		else next.add(tag);
		selectedTags = next;
		await onFilterChange();
	}

	function timePresetLabel(p: TimePreset): string {
		switch (p) {
			case '7':
				return $i18n.t('Last 7 Days');
			case '20':
				return $i18n.t('Last 20 Days');
			case '30':
				return $i18n.t('Last 30 Days');
			case 'all':
				return $i18n.t('All Time');
			case 'custom':
				return $i18n.t('Custom Range');
		}
	}

	function serializeMsgContent(content: unknown): string {
		if (typeof content === 'string') return content;
		if (content == null) return '';
		try {
			return JSON.stringify(content);
		} catch {
			return String(content);
		}
	}

	async function applyCustomRange() {
		if (!customStart || !customEnd) return;
		showCalendar = false;
		timePreset = 'custom';
		await onFilterChange();
	}

	function formatRowDate(ts: number): string {
		return dayjs.unix(ts).format('D MMM');
	}

	function formatMsgTime(ts?: number | null): string {
		if (ts == null) return '';
		return dayjs.unix(ts).format('LT');
	}

	/** List row only: strip leading emoji/s whitespace per UI spec (Unicode regex). */
	function displayChatListTitle(raw: string | undefined | null): string {
		const s = String(raw ?? '');
		const stripped = s.replace(/^[\p{Emoji}\s]+/u, '').trim();
		return stripped || s.trim();
	}

	async function openModal(row: AdminChatRow) {
		modalChat = row;
		modalOpen = true;
		modalLoading = true;
		modalMessages = [];
		try {
			modalMessages = await getAdminChatMessages(localStorage.token, row.id);
		} catch (e) {
			console.error(e);
			modalMessages = [];
		} finally {
			modalLoading = false;
		}
	}

	function closeModal() {
		modalOpen = false;
		modalChat = null;
		modalMessages = [];
	}

	function onBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) closeModal();
	}

	function onWindowKey(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			showCalendar = false;
			tagMenuOpen = false;
			if (modalOpen) closeModal();
		}
	}

	function handleWindowClick(e: MouseEvent) {
		const t = e.target;
		const el = t instanceof Element ? t : (t as Node).parentElement;
		if (!el) return;
		if (showCalendar && !el.closest('[data-calendar-root]')) showCalendar = false;
		if (tagMenuOpen && !el.closest('[data-tag-menu]')) tagMenuOpen = false;
	}

	onMount(async () => {
		window.addEventListener('keydown', onWindowKey);
		try {
			const [u, m] = await Promise.all([
				getUsers(localStorage.token),
				getModels(localStorage.token)
			]);
			adminUsers = u ?? [];
			modelsList = (m ?? []).map((x: { id: string; name: string }) => ({
				id: x.id,
				name: x.name
			}));
		} catch (e) {
			console.error(e);
		}
		await Promise.all([loadStats(), resetAndLoad()]);
		return () => window.removeEventListener('keydown', onWindowKey);
	});
</script>

<svelte:window on:click={handleWindowClick} />

<div class="admin-chats-page min-h-full -mx-[16px] bg-[#f9f9f9] px-4 pb-10 pt-2 dark:bg-gray-900 md:px-6">
	<div class="w-full">
		<!-- Documents: uploaded files + sensitivity validation (user & date align with filters below) -->
		<div class="mb-6 grid w-full grid-cols-2 gap-3" aria-live="polite">
			<div
				class="h-[72px] flex w-full min-w-0 items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850"
			>
				<div class="h-full w-[3px] shrink-0 bg-[#2EC4B6]"></div>
				<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
					<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">
						{$i18n.t('Total Documents')}
					</div>
					{#if statsLoading}
						<div class="mt-1 h-6 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
					{:else}
						<div
							class="mt-1 truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white"
						>
							{stats?.total_documents ?? 0}
						</div>
					{/if}
				</div>
			</div>
			<div
				class="h-[72px] flex w-full min-w-0 items-stretch rounded-[8px] border border-[#e8e8e8] bg-white dark:border-gray-700 dark:bg-gray-850"
			>
				<div class="h-full w-[3px] shrink-0 bg-[#F4845F]"></div>
				<div class="flex min-w-0 flex-1 flex-col justify-center px-4 py-[10px]">
					<div class="text-[11px] font-medium uppercase tracking-[0.04em] text-[#999]">
						{$i18n.t('Flagged Documents')}
					</div>
					{#if statsLoading}
						<div class="mt-1 h-6 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
					{:else}
						<div
							class="mt-1 truncate text-[20px] font-bold leading-none tabular-nums text-[#111] dark:text-white"
						>
							{stats?.flagged_documents ?? 0}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Filters: equal height, full width of column -->
		<div
			class="mb-6 grid w-full grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4 xl:items-stretch"
		>
			<select class="filter-dd w-full min-w-0" bind:value={userFilter} on:change={onFilterChange}>
				<option value="">{$i18n.t('All Users')}</option>
				{#each adminUsers as u}
					<option value={u.id}>{u.name || u.email || u.id}</option>
				{/each}
			</select>

			<select class="filter-dd w-full min-w-0" bind:value={modelFilter} on:change={onFilterChange}>
				<option value="">{$i18n.t('All Models')}</option>
				{#each modelsList as m}
					<option value={m.id}>{m.name}</option>
				{/each}
			</select>

			<div class="relative min-h-[2.75rem] min-w-0" data-tag-menu>
				<button
					type="button"
					class="filter-dd flex w-full min-w-0 items-center justify-between gap-2 text-left"
					on:click|stopPropagation={() => (tagMenuOpen = !tagMenuOpen)}
				>
				<span class="truncate">
					{#if selectedTags.size === 0}
						{$i18n.t('All Tags')}
					{:else}
						{[...selectedTags].slice(0, 2).join(', ')}{selectedTags.size > 2
							? ` +${selectedTags.size - 2}`
							: ''}
					{/if}
				</span>
				<span class="opacity-50 text-xs">▾</span>
			</button>
			{#if tagMenuOpen}
				<div
					class="absolute z-40 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-850 py-1 shadow-lg"
					transition:fade={{ duration: 100 }}
				>
					{#each TAG_OPTIONS as tag}
						<label
							class="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
						>
							<input
								type="checkbox"
								checked={selectedTags.has(tag)}
								on:change={() => toggleTag(tag)}
							/>
							{tag}
						</label>
					{/each}
				</div>
			{/if}
		</div>

			<div class="relative min-h-[2.75rem] min-w-0" data-calendar-root>
			<select
				class="filter-dd w-full min-w-0"
				bind:value={timePreset}
				on:change={async () => {
					if (timePreset === 'custom') {
						showCalendar = true;
						if (!customStart) {
							customStart = dayjs().subtract(7, 'day').format('YYYY-MM-DD');
						}
						if (!customEnd) {
							customEnd = dayjs().format('YYYY-MM-DD');
						}
					} else {
						showCalendar = false;
						await onFilterChange();
					}
				}}
			>
				<option value="all">{timePresetLabel('all')}</option>
				<option value="7">{timePresetLabel('7')}</option>
				<option value="20">{timePresetLabel('20')}</option>
				<option value="30">{timePresetLabel('30')}</option>
				<option value="custom">{timePresetLabel('custom')}</option>
			</select>

			{#if showCalendar && timePreset === 'custom'}
				<div
					class="absolute z-50 mt-1 w-[260px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-850 p-3 shadow-xl"
					transition:fade={{ duration: 120 }}
				>
					<p class="mb-2 text-xs font-medium text-gray-600 dark:text-gray-300">
						{$i18n.t('Custom Range')}
					</p>
					<div class="flex flex-col gap-2">
						<label class="text-xs text-gray-500">{$i18n.t('Start Date')}</label>
						<input type="date" class="filter-dd w-full" bind:value={customStart} />
						<label class="text-xs text-gray-500">{$i18n.t('End Date')}</label>
						<input type="date" class="filter-dd w-full" bind:value={customEnd} />
					</div>
					<div class="mt-3 flex justify-end gap-2">
						<button
							type="button"
							class="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800"
							on:click={() => {
								showCalendar = false;
							}}>{$i18n.t('Cancel')}</button
						>
						<button
							type="button"
							class="rounded-lg bg-gray-900 px-3 py-1.5 text-sm text-white dark:bg-white dark:text-gray-900"
							on:click={applyCustomRange}>{$i18n.t('Apply')}</button
						>
					</div>
				</div>
			{/if}
		</div>
		</div>

		<!-- Chat list -->
		<div
			class="w-full overflow-hidden rounded-xl border border-gray-200/90 bg-white/60 shadow-sm dark:border-zinc-700/90 dark:bg-zinc-900/50"
		>
		{#if loading && chats.length === 0}
			{#each Array(8) as _, i}
				<div
					class="animate-pulse border-b border-gray-100/90 py-[14px] pl-4 pr-4 last:border-b-0 dark:border-zinc-800/80 {i %
						2 ===
					0
						? 'bg-white/50 dark:bg-zinc-900/30'
						: 'bg-slate-50/80 dark:bg-zinc-800/25'}"
				>
					<div class="flex justify-between gap-4">
						<div class="h-4 flex-1 rounded bg-gray-200 dark:bg-gray-700"></div>
						<div class="h-4 w-32 rounded bg-gray-200 dark:bg-gray-700"></div>
					</div>
				</div>
			{/each}
		{:else if listError}
			<p class="py-8 text-center text-red-600">{listError}</p>
		{:else if chats.length === 0}
			<p class="py-16 text-center text-gray-500 dark:text-gray-400">
				{$i18n.t('No chats found')}
			</p>
		{:else}
			{#each chats as row, i}
				<button
					type="button"
					class="group flex w-full cursor-pointer items-center justify-between gap-3 border-b border-gray-100/90 py-[14px] pl-4 pr-4 text-left transition last:border-b-0 dark:border-zinc-800/80 {i %
						2 ===
					0
						? 'bg-white/70 dark:bg-zinc-900/35'
						: 'bg-slate-50/90 dark:bg-zinc-800/30'} hover:bg-indigo-50/70 dark:hover:bg-indigo-950/35"
					on:click={() => openModal(row)}
				>
					<span class="min-w-0 flex-1">
						<span
							class="block truncate text-sm font-medium text-gray-900 dark:text-white"
							title={row.titles_display || row.title}
						>
							{displayChatListTitle(row.titles_display || row.title)}
						</span>
						<span
							class="mt-0.5 block truncate text-[11px] text-indigo-600/75 dark:text-indigo-300/70"
						>
							{row.user?.name || row.user?.email || '—'}
						</span>
					</span>
					<div
						class="ml-2 flex shrink-0 flex-wrap items-center justify-end gap-x-2 gap-y-1 whitespace-nowrap text-sm"
					>
						<span class="text-violet-600/80 dark:text-violet-300/75">{formatRowDate(row.updated_at)}</span>
						<span class="text-gray-300 dark:text-zinc-600" aria-hidden="true">·</span>
						<span class="font-medium text-slate-600 dark:text-slate-300"
							>{row.message_count} {$i18n.t('messages')}</span
						>
					</div>
				</button>
			{/each}
			<div bind:this={sentinel} class="h-4 w-full" aria-hidden="true"></div>
			{#if loadingMore}
				<p class="py-4 text-center text-sm text-gray-400">{$i18n.t('Loading…')}</p>
			{/if}
		{/if}
		</div>
	</div>
</div>

{#if modalOpen && modalChat}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<div
		class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 px-4 py-6"
		on:click={onBackdropClick}
		on:keydown|stopPropagation
		transition:fade={{ duration: 150 }}
		role="presentation"
	>
		<div
			class="relative flex max-h-[80vh] w-full max-w-[720px] flex-col overflow-hidden rounded-xl bg-white shadow-[0_8px_40px_rgba(0,0,0,0.2)] dark:bg-gray-900"
			transition:scale={{ duration: 160, start: 0.97 }}
			on:click|stopPropagation
			role="dialog"
			aria-modal="true"
			tabindex="-1"
		>
			<div class="flex items-start justify-between gap-4 border-b border-gray-100 px-6 py-4 dark:border-gray-800">
				<h2 class="pr-8 text-lg font-semibold text-gray-900 dark:text-white">
					{modalChat.title}
				</h2>
				<button
					type="button"
					class="rounded-lg p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					aria-label={$i18n.t('Close')}
					on:click={closeModal}
				>
					✕
				</button>
			</div>

			<div class="flex-1 overflow-y-auto px-6 py-4">
				{#if modalLoading}
					<p class="text-center text-gray-500">{$i18n.t('Loading…')}</p>
				{:else}
					<div class="flex flex-col gap-4">
						{#each modalMessages as msg, idx}
							<div
								class={`flex max-w-[95%] flex-col gap-1 ${msg.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'}`}
							>
								<div class="mb-0.5 flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
									<span class="font-medium uppercase">{msg.role}</span>
									{#if msg.model_name || msg.model}
										<span class="text-gray-400">· {msg.model_name || msg.model}</span>
									{/if}
									{#if msg.timestamp}
										<span>· {formatMsgTime(msg.timestamp)}</span>
									{/if}
								</div>
								<div
									class={`max-w-full rounded-2xl px-4 py-2.5 text-sm ${msg.role === 'user' ? 'rounded-br-sm bg-[#3B4BC8] text-white [&_.prose]:text-white' : msg.role === 'system' ? 'rounded-md bg-amber-50 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100' : 'rounded-bl-sm bg-[#f0f0f0] text-gray-900 dark:bg-gray-800 dark:text-gray-100'}`}
								>
									{#if msg.role === 'assistant'}
										<Markdown
											id={`adm-${modalChat.id}-${idx}`}
											content={serializeMsgContent(msg.content)}
										/>
									{:else if msg.role === 'user'}
										<div class="[&_.markdown-prose]:!text-white [&_*]:!text-white">
											<Markdown
												id={`adm-${modalChat.id}-u-${idx}`}
												content={serializeMsgContent(msg.content)}
											/>
										</div>
									{:else}
										<div class="whitespace-pre-wrap break-words font-mono text-xs">
											{serializeMsgContent(msg.content)}
										</div>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<div class="flex justify-end gap-3 border-t border-gray-100 px-6 py-4 dark:border-gray-800">
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
					on:click={closeModal}>{$i18n.t('Close')}</button
				>
			</div>
		</div>
	</div>
{/if}

<style>
	.filter-dd {
		@apply box-border min-h-[2.75rem] rounded-lg border border-[#e0e0e0] bg-white px-[14px] py-2 text-[14px] leading-normal text-gray-900 outline-none dark:border-gray-700 dark:bg-gray-850 dark:text-white;
	}
</style>
