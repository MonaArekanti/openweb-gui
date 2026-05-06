<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import AddConnectionModal from './AddConnectionModal.svelte';

	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import PencilSolid from '$lib/components/icons/PencilSolid.svelte';

	export let onDelete = () => {};
	export let onSubmit = () => {};
	/** When inline URL edit commits and the base URL changes */
	export let onMigrateUrl: (from: string, to: string) => void = () => {};

	export let url = '';
	export let config: Record<string, unknown> = {};

	/** null = checking */
	export let reachable: boolean | null = null;

	let showConfigModal = false;
	let editingUrl = false;
	let draftUrl = url;

	$: if (!editingUrl) draftUrl = url;

	$: connectionForModal = {
		url,
		key: typeof config?.key === 'string' ? config.key : '',
		config
	};
</script>

<tr class="border-b border-[#f0f0f0] bg-white last:border-b-0 dark:border-gray-800 dark:bg-gray-900">
	<td class="min-w-0 px-4 py-3 align-middle text-left">
		{#if !(config?.enable ?? true)}
			<div class="pointer-events-none opacity-50">{url}</div>
		{:else if editingUrl}
			<input
				class="w-full rounded-md border border-gray-200 bg-white px-2 py-1 text-[14px] text-gray-900 outline-none dark:border-gray-600 dark:bg-gray-850 dark:text-white"
				bind:value={draftUrl}
				placeholder={$i18n.t('Enter URL (e.g. http://localhost:11434)')}
				autocomplete="off"
			/>
		{:else}
			<div class="truncate text-[14px] font-medium text-gray-900 dark:text-white" title={url}>
				{url}
			</div>
		{/if}
	</td>
	<td class="px-4 py-3 align-middle whitespace-nowrap text-left">
		{#if reachable === null}
			<span class="text-[13px] text-gray-400">…</span>
		{:else if reachable}
			<span class="inline-flex items-center gap-2 text-[13px] font-medium text-green-600 dark:text-green-400">
				<span class="h-2 w-2 shrink-0 rounded-full bg-green-500"></span>
				{$i18n.t('Active')}
			</span>
		{:else}
			<span class="inline-flex items-center gap-2 text-[13px] font-medium text-red-600 dark:text-red-400">
				<span class="h-2 w-2 shrink-0 rounded-full bg-red-500"></span>
				{$i18n.t('Inactive')}
			</span>
		{/if}
	</td>
	<td class="px-4 py-3 align-middle text-right whitespace-nowrap">
		<div class="inline-flex w-full items-center justify-end gap-0.5">
			<Tooltip content={$i18n.t('Edit URL')} className="inline-flex">
				<button
					type="button"
					class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-850 dark:hover:text-white"
					on:click={() => {
						editingUrl = !editingUrl;
						draftUrl = url;
					}}
					aria-label={$i18n.t('Edit URL')}
				>
					<PencilSolid className="h-[18px] w-[18px]" />
				</button>
			</Tooltip>
			{#if editingUrl}
				<button
					type="button"
					class="rounded-lg px-2 py-1 text-xs font-medium text-[#2EC4B6] hover:underline"
					on:click={() => {
						const prev = url;
						const next = draftUrl.replace(/\/$/, '');
						url = next;
						if (prev !== next) {
							onMigrateUrl(prev, next);
						}
						editingUrl = false;
						onSubmit();
					}}
				>
					{$i18n.t('Apply')}
				</button>
			{/if}
			<Tooltip content={$i18n.t('Configure')} className="inline-flex">
				<button
					type="button"
					class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-850 dark:hover:text-white"
					on:click={() => (showConfigModal = true)}
					aria-label={$i18n.t('Configure')}
				>
					<Cog6 className="h-[18px] w-[18px]" strokeWidth="1.75" />
				</button>
			</Tooltip>
		</div>
	</td>
</tr>

<AddConnectionModal
	ollama
	edit
	bind:show={showConfigModal}
	connection={connectionForModal}
	{onDelete}
	onSubmit={(c) => {
		url = c.url;
		config = { ...c.config, key: c.key };
		onSubmit(c);
	}}
/>
