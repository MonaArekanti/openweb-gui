<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';

	import { WEBUI_NAME, showSidebar, user } from '$lib/stores';
	import MenuLines from '$lib/components/icons/MenuLines.svelte';
	import { page } from '$app/stores';

	const i18n = getContext('i18n');

	let loaded = false;

	function tabClass(href: string): string {
		const p = $page.url.pathname;
		let active = false;
		if (href === '/admin/users') {
			active = p === '/admin' || p === '/admin/users';
		} else {
			active = p === href || p.startsWith(href + '/');
		}
		return active
			? 'font-semibold text-gray-900 dark:text-white'
			: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white';
	}

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
		}
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Admin Panel')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div
		class=" flex flex-col w-full min-h-screen max-h-screen {$showSidebar
			? 'md:max-w-[calc(100%-260px)]'
			: ''}"
	>
		<div class=" px-2.5 py-1 backdrop-blur-xl">
			<div class=" flex items-center gap-1">
				<div class="{$showSidebar ? 'md:hidden' : ''} flex flex-none items-center">
					<button
						id="sidebar-toggle-button"
						class="cursor-pointer p-1.5 flex rounded-xl hover:bg-gray-100 dark:hover:bg-gray-850 transition"
						on:click={() => {
							showSidebar.set(!$showSidebar);
						}}
						aria-label="Toggle Sidebar"
					>
						<div class=" m-auto self-center">
							<MenuLines />
						</div>
					</button>
				</div>

				<div class=" flex w-full">
					<div
						class="flex gap-1 scrollbar-none overflow-x-auto w-fit text-center text-sm font-medium rounded-full bg-transparent pt-1"
					>
						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/users')}"
							href="/admin/users">{$i18n.t('Users')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/analytics')}"
							href="/admin/analytics">{$i18n.t('Analytics')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/tokens')}"
							href="/admin/tokens">{$i18n.t('Tokens')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/chats')}"
							href="/admin/chats">{$i18n.t('Chats')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/evaluations')}"
							href="/admin/evaluations">{$i18n.t('Evaluations')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/functions')}"
							href="/admin/functions">{$i18n.t('Functions')}</a
						>

						<a
							class="min-w-fit rounded-full p-1.5 transition {tabClass('/admin/settings')}"
							href="/admin/settings">{$i18n.t('Settings')}</a
						>
					</div>
				</div>
			</div>
		</div>

		<div class=" pb-1 px-[16px] flex-1 max-h-full overflow-y-auto">
			<slot />
		</div>
	</div>
{/if}
