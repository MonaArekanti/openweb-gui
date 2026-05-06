<script>
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';
	import { getUsers } from '$lib/apis/users';
	import UserList from './Users/UserList.svelte';
	import Groups from './Users/Groups.svelte';

	const i18n = getContext('i18n');

	let users = [];
	let selectedTab = 'overview';

	$: if (selectedTab) {
		getUsersHandler();
	}

	const getUsersHandler = async () => {
		users = await getUsers(localStorage.token);
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}

		users = await getUsers(localStorage.token);
	});
</script>

<div class="w-full h-full pb-2">
	<div class="flex items-center gap-6 overflow-x-auto border-b border-gray-200 dark:border-gray-800 mb-4">
		<button
			class="text-sm py-2 border-b-2 transition-colors duration-200 {selectedTab === 'overview'
				? 'font-bold text-[#111111] dark:text-white border-[#111111] dark:border-white'
				: 'font-medium text-[#999999] dark:text-gray-500 border-transparent hover:text-gray-700 dark:hover:text-gray-300'}"
			on:click={() => {
				selectedTab = 'overview';
			}}
		>
			{$i18n.t('Overview')}
		</button>

		<button
			class="text-sm py-2 border-b-2 transition-colors duration-200 {selectedTab === 'groups'
				? 'font-bold text-[#111111] dark:text-white border-[#111111] dark:border-white'
				: 'font-medium text-[#999999] dark:text-gray-500 border-transparent hover:text-gray-700 dark:hover:text-gray-300'}"
			on:click={() => {
				selectedTab = 'groups';
			}}
		>
			{$i18n.t('Groups')}
		</button>
	</div>

	<div class="overflow-y-auto">
		{#if selectedTab === 'overview'}
			<UserList {users} />
		{:else if selectedTab === 'groups'}
			<Groups {users} />
		{/if}
	</div>
</div>
