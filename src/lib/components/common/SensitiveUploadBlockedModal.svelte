<script lang="ts">
	import { getContext } from 'svelte';
	import { fade } from 'svelte/transition';
	import { sensitiveUploadBlockedModalOpen } from '$lib/stores';

	const i18n = getContext('i18n');

	function close() {
		sensitiveUploadBlockedModalOpen.set(false);
	}
</script>

{#if $sensitiveUploadBlockedModalOpen}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<div
		class="fixed inset-0 z-[10050] flex items-center justify-center p-4"
		transition:fade={{ duration: 150 }}
		role="presentation"
	>
		<div
			class="absolute inset-0 bg-black/50 backdrop-blur-sm dark:bg-black/60"
			aria-hidden="true"
		></div>
		<div
			class="relative z-10 w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-850"
			role="alertdialog"
			aria-modal="true"
			aria-labelledby="sensitive-upload-title"
		>
			<div class="flex items-start justify-between gap-4">
				<h2 id="sensitive-upload-title" class="text-lg font-semibold text-gray-900 dark:text-white pr-8">
					{$i18n.t('Sensitive content detected. This document cannot be uploaded.')}
				</h2>
				<button
					type="button"
					class="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white"
					aria-label={$i18n.t('Close')}
					on:click={close}
				>
					<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="mt-8 flex justify-end">
				<button
					type="button"
					class="rounded-xl bg-gray-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					on:click={close}
				>
					{$i18n.t('OK')}
				</button>
			</div>
		</div>
	</div>
{/if}
