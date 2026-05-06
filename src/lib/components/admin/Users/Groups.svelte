<script>
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import UsersSolid from '$lib/components/icons/UsersSolid.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import GroupModal from './Groups/EditGroupModal.svelte';
	import GroupItem from './Groups/GroupItem.svelte';
	import AddGroupModal from './Groups/AddGroupModal.svelte';
	import { createNewGroup, getGroups } from '$lib/apis/groups';
	import { getUserDefaultPermissions, updateUserDefaultPermissions } from '$lib/apis/users';

	const i18n = getContext('i18n');

	let loaded = false;
	export let users = [];
	let groups = [];
	let filteredGroups;
	let search = '';
	let defaultPermissions = {
		workspace: {
			models: false,
			knowledge: false,
			prompts: false,
			tools: false
		},
		chat: {
			file_upload: true,
			delete: true,
			edit: true,
			temporary: true
		}
	};

	let showCreateGroupModal = false;
	let showDefaultPermissionsModal = false;

	$: filteredGroups = groups.filter((group) => {
		if (search === '') return true;
		return group.name.toLowerCase().includes(search.toLowerCase());
	});

	const setGroups = async () => {
		groups = await getGroups(localStorage.token);
	};

	const addGroupHandler = async (group) => {
		const res = await createNewGroup(localStorage.token, group).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group created successfully'));
			groups = await getGroups(localStorage.token);
		}
	};

	const updateDefaultPermissionsHandler = async (group) => {
		const res = await updateUserDefaultPermissions(localStorage.token, group.permissions).catch(
			(error) => {
				toast.error(error);
				return null;
			}
		);

		if (res) {
			toast.success($i18n.t('Default permissions updated successfully'));
			defaultPermissions = await getUserDefaultPermissions(localStorage.token);
		}
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
		} else {
			await setGroups();
			defaultPermissions = await getUserDefaultPermissions(localStorage.token);
		}
		loaded = true;
	});
</script>

{#if loaded}
	<AddGroupModal bind:show={showCreateGroupModal} onSubmit={addGroupHandler} />

	<div class="mb-4 gap-3 flex flex-col md:flex-row md:items-center md:justify-between">
		<div class="flex items-center">
			<h2 class="text-[22px] leading-none font-bold text-gray-900 dark:text-gray-100">
				{$i18n.t('Groups')}
			</h2>
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
						d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 0 0 0-11zM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9z"
						clip-rule="evenodd"
					/>
				</svg>
				<input
					class="w-full text-sm pl-2 outline-none bg-transparent text-gray-700 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
					bind:value={search}
					placeholder={$i18n.t('Search')}
				/>
			</div>

			<Tooltip content={$i18n.t('Create Group')}>
				<button
					class="h-10 w-10 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:text-[#111111] dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-200"
					on:click={() => {
						showCreateGroupModal = !showCreateGroupModal;
					}}
				>
					<Plus className="size-4" />
				</button>
			</Tooltip>
		</div>
	</div>

	<div>
		{#if filteredGroups.length === 0}
			<div class="flex flex-col items-center justify-center h-40">
				<div class="text-xl font-medium">{$i18n.t('Organize your users')}</div>
				<div class="mt-1 text-sm dark:text-gray-300">
					{$i18n.t('Use groups to group your users and assign permissions.')}
				</div>
				<div class="mt-3">
					<button
						class="px-4 py-1.5 text-sm rounded-full bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition font-medium flex items-center space-x-1"
						aria-label={$i18n.t('Create Group')}
						on:click={() => {
							showCreateGroupModal = true;
						}}
					>
						{$i18n.t('Create Group')}
					</button>
				</div>
			</div>
		{:else}
			<div
				class="groups-table w-full overflow-x-auto rounded-xl border border-[#e8e8e8] dark:border-gray-800 shadow-[0_1px_6px_rgba(0,0,0,0.05)] bg-white dark:bg-gray-900"
			>
				<table class="w-full min-w-[720px] text-left table-auto">
					<colgroup>
						<col class="w-[420px]" />
						<col class="w-[200px]" />
						<col class="w-[120px]" />
					</colgroup>
					<thead class="bg-[#fafafa] dark:bg-gray-850 border-b border-[#e8e8e8] dark:border-gray-800">
						<tr
							class="text-[11px] uppercase tracking-[0.06em] text-[#999999] dark:text-gray-400 font-semibold"
						>
							<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Group')}</th>
							<th scope="col" class="px-4 py-2.5 align-middle">{$i18n.t('Users')}</th>
							<th scope="col" class="px-4 py-2.5 align-middle text-right">
								{$i18n.t('Actions')}
							</th>
						</tr>
					</thead>
					<tbody>
						{#each filteredGroups as group}
							<GroupItem {group} {users} {setGroups} />
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		<hr class="mb-2 mt-3 border-gray-50 dark:border-gray-850" />

		<GroupModal
			bind:show={showDefaultPermissionsModal}
			tabs={['permissions']}
			bind:permissions={defaultPermissions}
			custom={false}
			onSubmit={updateDefaultPermissionsHandler}
		/>

		<button
			class="flex items-center justify-between rounded-lg w-full transition pt-1"
			on:click={() => {
				showDefaultPermissionsModal = true;
			}}
		>
			<div class="flex items-center gap-2.5">
				<div class="p-1.5 bg-black/5 dark:bg-white/10 rounded-full">
					<UsersSolid className="size-4" />
				</div>
				<div class="text-left">
					<div class="text-sm font-medium">{$i18n.t('Default permissions')}</div>
					<div class="flex text-xs mt-0.5">
						{$i18n.t('applies to all users with the "user" role')}
					</div>
				</div>
			</div>
			<div>
				<ChevronRight strokeWidth="2.5" />
			</div>
		</button>
	</div>
{/if}

<style>
	.groups-table :global(tbody tr:last-child) {
		border-bottom: none;
	}
</style>
