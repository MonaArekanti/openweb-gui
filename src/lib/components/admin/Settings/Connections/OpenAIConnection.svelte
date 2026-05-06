<script lang="ts">
	import { getContext } from 'svelte';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import AddConnectionModal from './AddConnectionModal.svelte';

	const i18n = getContext('i18n');

	const OPENAI_PROVIDER_BASES: [string, string][] = [
		['https://api.openai.com/v1', 'OpenAI'],
		['https://api.groq.com/openai/v1', 'Groq'],
		['https://api.mistral.ai/v1', 'Mistral'],
		['https://openrouter.ai/api/v1', 'OpenRouter']
	];

	function openAiProviderLabel(rawUrl: string): string {
		const trimmed = rawUrl.trim().replace(/\/+$/, '');
		const lower = trimmed.toLowerCase();
		for (const [base, label] of OPENAI_PROVIDER_BASES) {
			if (lower === base || lower.startsWith(`${base}/`)) {
				return label;
			}
		}
		return '—';
	}

	export let onDelete = () => {};
	export let onSubmit = () => {};

	export let pipeline = false;

	export let url = '';
	export let key = '';
	export let config: Record<string, unknown> = {};

	/** null = checking */
	export let reachable: boolean | null = null;

	let showConfigModal = false;
</script>

<tr class="border-b border-[#f0f0f0] bg-white last:border-b-0 dark:border-gray-800 dark:bg-gray-900">
	<td class="min-w-0 px-4 py-3 align-middle text-left">
		{#if !(config?.enable ?? true)}
			<div class="pointer-events-none opacity-50">{url}</div>
		{:else}
			<div class="truncate text-[14px] font-medium text-gray-900 dark:text-white" title={url}>
				{url}
			</div>
		{/if}
		{#if pipeline}
			<div class="mt-0.5 text-[11px] text-gray-400">{$i18n.t('Pipeline')}</div>
		{/if}
	</td>
	<td class="px-4 py-3 align-middle text-left">
		{#if !(config?.enable ?? true)}
			<div class="pointer-events-none truncate text-[13px] text-gray-700 opacity-50 dark:text-gray-300">
				{openAiProviderLabel(url)}
			</div>
		{:else}
			<div
				class="truncate text-[13px] text-gray-700 dark:text-gray-300"
				title={openAiProviderLabel(url)}
			>
				{openAiProviderLabel(url)}
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
		<Tooltip content={$i18n.t('Configure')} className="inline-flex justify-end">
			<button
				type="button"
				class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-850 dark:hover:text-white"
				on:click={() => (showConfigModal = true)}
				aria-label={$i18n.t('Configure')}
			>
				<Cog6 className="h-[18px] w-[18px]" strokeWidth="1.75" />
			</button>
		</Tooltip>
	</td>
</tr>

<AddConnectionModal
	edit
	bind:show={showConfigModal}
	connection={{
		url,
		key,
		config
	}}
	{onDelete}
	onSubmit={(c) => {
		url = c.url;
		key = c.key;
		config = { ...c.config };
		onSubmit(c);
	}}
/>
