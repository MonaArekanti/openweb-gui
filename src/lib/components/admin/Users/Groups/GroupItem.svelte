<script>
	import { toast } from 'svelte-sonner';
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	import { deleteGroupById, updateGroupById } from '$lib/apis/groups';

	import GroupModal from './EditGroupModal.svelte';

	export let users = [];
	export let group = {
		name: 'Admins',
		user_ids: [1, 2, 3]
	};

	export let setGroups = () => {};

	let showEdit = false;

	const updateHandler = async (_group) => {
		const res = await updateGroupById(localStorage.token, group.id, _group).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group updated successfully'));
			setGroups();
		}
	};

	const deleteHandler = async () => {
		const res = await deleteGroupById(localStorage.token, group.id).catch((error) => {
			toast.error(error);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group deleted successfully'));
			setGroups();
		}
	};
</script>

<GroupModal
	bind:show={showEdit}
	edit
	{users}
	{group}
	onSubmit={updateHandler}
	onDelete={deleteHandler}
/>

<tr
	class="bg-white dark:bg-gray-900 hover:bg-[#f9fafb] dark:hover:bg-gray-850 transition-colors duration-200 border-b border-[#f5f5f5] dark:border-gray-800"
>
	<td class="px-4 py-3.5 align-middle text-sm text-[#111111] dark:text-gray-100 font-medium">
		{group.name}
	</td>
	<td class="px-4 py-3.5 align-middle text-[13px] text-[#666666] dark:text-gray-400">
		{group.user_ids.length}
	</td>
	<td class="px-4 py-3.5 align-middle text-right">
		<button
			class="inline-flex items-center text-[#999999] dark:text-gray-500 hover:text-[#111111] dark:hover:text-gray-100 transition-colors duration-200"
			on:click={() => {
				showEdit = true;
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
	</td>
</tr>
