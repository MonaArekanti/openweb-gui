<script>
	import AdminChats from '$lib/components/admin/AdminChats.svelte';
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');
</script>

<div class="w-full max-w-6xl pb-4">
	<h1 class="mb-6 text-2xl font-bold text-gray-900 dark:text-white">{$i18n.t('Chats')}</h1>
	<AdminChats />
</div>
