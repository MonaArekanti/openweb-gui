<script>
	import { getContext, onMount } from 'svelte';
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { updateUserRole, getUsers } from '$lib/apis/users';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import AddUserModal from '$lib/components/admin/Users/UserList/AddUserModal.svelte';
	import EditUserModal from '$lib/components/admin/Users/UserList/EditUserModal.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	dayjs.extend(relativeTime);

	const i18n = getContext('i18n');
	const PAGE_SIZE = 20;

	export let users = [];

	let search = '';
	let selectedUser = null;
	let showAddUserModal = false;
	let showEditUserModal = false;
	let sortOrder = 'desc';
	let visibleCount = PAGE_SIZE;
	let loadingMore = false;
	let sentinelElement;
	let observer;
	let paginationKey = '';

	const updateRoleHandler = async (id, role) => {
		const res = await updateUserRole(localStorage.token, id, role).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			users = await getUsers(localStorage.token);
		}
	};

	const toggleCreatedAtSort = () => {
		sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
	};

	$: filteredUsers = users.filter((item) => {
		if (!search) {
			return true;
		}
		const query = search.toLowerCase();
		return item.name.toLowerCase().includes(query) || item.email.toLowerCase().includes(query);
	});

	$: sortedUsers = [...filteredUsers].sort((a, b) =>
		sortOrder === 'asc' ? a.created_at - b.created_at : b.created_at - a.created_at
	);
	$: hasMore = sortedUsers.length > visibleCount;
	$: displayedUsers = sortedUsers.slice(0, visibleCount);

	$: {
		const nextKey = `${search}|${sortOrder}|${users.length}`;
		if (nextKey !== paginationKey) {
			paginationKey = nextKey;
			visibleCount = PAGE_SIZE;
		}
	}

	const loadMoreUsers = async () => {
		if (!hasMore || loadingMore) return;

		loadingMore = true;
		await new Promise((resolve) => setTimeout(resolve, 220));
		visibleCount = Math.min(visibleCount + PAGE_SIZE, sortedUsers.length);
		loadingMore = false;
	};

	onMount(() => {
		observer = new IntersectionObserver(
			(entries) => {
				if (entries[0]?.isIntersecting) {
					loadMoreUsers();
				}
			},
			{ threshold: 0.2 }
		);

		return () => observer?.disconnect();
	});

	$: if (observer && sentinelElement) {
		observer.disconnect();
		observer.observe(sentinelElement);
	}
</script>

{#key selectedUser}
	<EditUserModal
		bind:show={showEditUserModal}
		{selectedUser}
		sessionUser={$user}
		on:save={async () => {
			users = await getUsers(localStorage.token);
		}}
	/>
{/key}

<AddUserModal
	bind:show={showAddUserModal}
	on:save={async () => {
		users = await getUsers(localStorage.token);
	}}
/>

<div class="mb-4 gap-3 flex flex-col md:flex-row md:items-center md:justify-between">
	<div class="flex items-center">
		<h2 class="text-[22px] leading-none font-bold text-gray-900 dark:text-gray-100">{$i18n.t('Users')}</h2>
	</div>

	<div class="flex items-center gap-2">
		<div
			class="w-full md:w-[200px] h-10 rounded-lg border border-[#e0e0e0] dark:border-gray-700 bg-white dark:bg-gray-900 flex items-center px-3"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 20 20"
				fill="currentColor"
				class="w-4 h-4 text-gray-400 dark:text-gray-500"
			>
				<path
					fill-rule="evenodd"
					d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
					clip-rule="evenodd"
				/>
			</svg>
			<input
				class="w-full text-sm pl-2 outline-none bg-transparent text-gray-700 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
				bind:value={search}
				placeholder={$i18n.t('Search')}
			/>
		</div>

		<Tooltip content={$i18n.t('Add User')}>
			<button
				class="h-10 w-10 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:text-[#111111] dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-200"
				on:click={() => {
					showAddUserModal = !showAddUserModal;
				}}
			>
				<Plus className="size-4" />
			</button>
		</Tooltip>
	</div>
</div>

<div
	class="w-full overflow-x-auto rounded-xl border border-[#e8e8e8] dark:border-gray-800 shadow-[0_1px_6px_rgba(0,0,0,0.05)] bg-white dark:bg-gray-900"
>
	<table class="w-full min-w-[720px] text-left table-auto">
		<colgroup>
			<col class="w-[140px]" />
			<col class="w-[200px]" />
			<col class="w-[260px]" />
			<col class="w-[180px]" />
			<col class="w-[160px]" />
			<col class="w-[120px]" />
		</colgroup>
		<thead class="bg-[#fafafa] dark:bg-gray-850 border-b border-[#e8e8e8] dark:border-gray-800">
			<tr class="text-[11px] uppercase tracking-[0.06em] text-[#999999] dark:text-gray-400 font-semibold">
				<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Role')}</th>
				<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Name')}</th>
				<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Email')}</th>
				<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Last Active')}</th>
				<th
					scope="col"
					class="px-4 py-2.5 align-middle cursor-pointer select-none"
					on:click={toggleCreatedAtSort}
				>
					<div class="flex items-center gap-1">
						{$i18n.t('Created At')}
						<span class="text-[10px] leading-none text-[#9ca3af] dark:text-gray-500"
							>{sortOrder === 'asc' ? '↑' : '↓'}</span
						>
					</div>
				</th>
				<th scope="col" class="px-4 py-2.5 align-middle text-right">{$i18n.t('Actions')}</th>
			</tr>
		</thead>

		<tbody>
			{#each displayedUsers as user, userIdx}
				<tr
					class="bg-white dark:bg-gray-900 hover:bg-[#f9fafb] dark:hover:bg-gray-850 transition-colors duration-200 {userIdx === displayedUsers.length - 1
						? ''
						: 'border-b border-[#f5f5f5] dark:border-gray-800'}"
				>
					<td class="px-4 py-3.5 align-middle">
						<button
							on:click={() => {
								if (user.role === 'user') {
									updateRoleHandler(user.id, 'admin');
								} else if (user.role === 'pending') {
									updateRoleHandler(user.id, 'user');
								} else {
									updateRoleHandler(user.id, 'pending');
								}
							}}
						>
							<span
								class="inline-flex items-center rounded-md px-2.5 py-0.5 text-[11px] font-bold uppercase {user.role ===
								'admin'
									? 'bg-[#dbeafe] text-[#1d4ed8] dark:bg-blue-500/20 dark:text-blue-300'
									: 'bg-[#f3f4f6] text-[#374151] dark:bg-gray-700 dark:text-gray-200'}"
							>
								{$i18n.t(user.role)}
							</span>
						</button>
					</td>
					<td class="px-4 py-3.5 align-middle text-sm text-[#111111] dark:text-gray-100 font-medium">
						{user.name}
					</td>
					<td class="px-4 py-3.5 align-middle text-[13px] text-[#666666] dark:text-gray-400">
						{user.email}
					</td>
					<td class="px-4 py-3.5 align-middle text-[13px] text-[#666666] dark:text-gray-400">
						{dayjs(user.last_active_at * 1000).fromNow()}
					</td>
					<td class="px-4 py-3.5 align-middle text-[13px] text-[#666666] dark:text-gray-400">
						{dayjs(user.created_at * 1000).format('MMM DD, YYYY')}
					</td>
					<td class="px-4 py-3.5 align-middle text-right">
						<Tooltip content={$i18n.t('Edit User')}>
							<button
								class="inline-flex items-center text-[#999999] dark:text-gray-500 hover:text-[#111111] dark:hover:text-gray-100 transition-colors duration-200"
								on:click={async () => {
									showEditUserModal = !showEditUserModal;
									selectedUser = user;
								}}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="w-4 h-4"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
									/>
								</svg>
							</button>
						</Tooltip>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>

	{#if displayedUsers.length === 0}
		<div class="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">{$i18n.t('No users found')}</div>
	{/if}
</div>

<div bind:this={sentinelElement} class="h-8 flex items-center justify-center">
	{#if loadingMore && sortedUsers.length > PAGE_SIZE}
		<div
			class="w-4 h-4 border-2 border-gray-300 dark:border-gray-700 border-t-gray-500 dark:border-t-gray-300 rounded-full animate-spin"
		/>
	{/if}
</div>
