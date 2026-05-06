<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		getModelPermissions,
		patchModelPermission,
		type ModelPermissionRow
	} from '$lib/apis/modelPermissions';
	import { getModels } from '$lib/apis';
	import { models } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';

	const i18n = getContext('i18n');

	let rows: ModelPermissionRow[] = [];
	let loading = true;
	let error: string | null = null;
	/** Avoid PATCH when Switch syncs from initial row data. */
	let allowSave = false;

	async function load() {
		allowSave = false;
		loading = true;
		error = null;
		try {
			rows = await getModelPermissions(localStorage.token);
		} catch (e: any) {
			error =
				(typeof e?.detail === 'object' && e?.detail?.detail) ||
				e?.detail ||
				String(e);
			rows = [];
		} finally {
			loading = false;
			await tick();
			allowSave = true;
		}
	}

	onMount(load);

	async function save(row: ModelPermissionRow, field: 'users_enabled' | 'groups_enabled') {
		if (!allowSave) return;
		try {
			const updated = await patchModelPermission(localStorage.token, row.model_id, {
				[field]: row[field]
			});
			const idx = rows.findIndex((r) => r.model_id === updated.model_id);
			if (idx >= 0) rows[idx] = updated;
			rows = rows;
			toast.success($i18n.t('Saved'), { duration: 1400 });
			try {
				const list = await getModels(localStorage.token);
				models.set(list);
			} catch {
				/* store refresh best-effort */
			}
		} catch (e: any) {
			toast.error(
				typeof e?.detail === 'object' ? e?.detail?.detail ?? $i18n.t('Failed to save') : $i18n.t('Failed to save')
			);
			await load();
		}
	}
</script>

<div class="flex h-full flex-col justify-between text-sm">
	<div class="scrollbar-hidden h-full overflow-y-scroll">
		<div class="my-2 pr-1.5">
			<div class="mb-4 text-base font-bold text-gray-900 dark:text-white">
				{$i18n.t('Permissions')}
			</div>
			<p class="mb-4 max-w-3xl text-sm text-gray-600 dark:text-gray-400">
				{$i18n.t(
					'Control which models appear for normal users in personal chats versus shared/group chats. Admins always see all models.'
				)}
			</p>

			{#if loading}
				<div class="flex justify-center py-12">
					<div
						class="h-10 w-10 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"
					/>
				</div>
			{:else if error}
				<p class="text-sm text-red-600">{error}</p>
				<button type="button" class="mt-2 text-sm underline" on:click={load}
					>{$i18n.t('Retry')}</button
				>
			{:else if rows.length === 0}
				<p class="text-sm text-gray-500">
					{$i18n.t('No models found. Configure connections first.')}
				</p>
			{:else}
				<div
					class="overflow-hidden rounded-lg border border-[#e0e0e0] bg-white dark:border-gray-600 dark:bg-gray-900"
				>
					<table class="w-full table-fixed border-collapse text-sm">
						<colgroup>
							<col />
							<col style="width: 140px" />
							<col style="width: 120px" />
							<col style="width: 120px" />
						</colgroup>
						<thead>
							<tr
								class="border-b border-[#e5e7eb] bg-[#f9fafb] dark:border-gray-700 dark:bg-gray-850"
							>
								<th
									class="px-4 py-3.5 text-left text-[13px] font-bold text-gray-900 dark:text-white"
									scope="col">{$i18n.t('Model Name')}</th
								>
								<th
									class="px-4 py-3.5 text-left text-[13px] font-bold text-gray-900 dark:text-white"
									scope="col">{$i18n.t('Provider')}</th
								>
								<th
									class="px-4 py-3.5 text-center text-[13px] font-bold text-gray-900 dark:text-white"
									scope="col">{$i18n.t('Users')}</th
								>
								<th
									class="px-4 py-3.5 text-center text-[13px] font-bold text-gray-900 dark:text-white"
									scope="col">{$i18n.t('Groups')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each rows as row (row.model_id)}
								<tr
									class="border-b border-[#e5e7eb] bg-white last:border-b-0 dark:border-gray-700 dark:bg-gray-900"
								>
									<td class="px-4 py-3.5 align-middle font-medium text-gray-900 dark:text-white"
										>{row.model_name}</td
									>
									<td class="px-4 py-3.5 align-middle text-gray-700 dark:text-gray-300"
										>{row.provider}</td
									>
									<td class="px-4 py-3.5 align-middle text-center">
										<div class="flex justify-center">
											<Switch
												bind:state={row.users_enabled}
												on:change={() => save(row, 'users_enabled')}
											/>
										</div>
									</td>
									<td class="px-4 py-3.5 align-middle text-center">
										<div class="flex justify-center">
											<Switch
												bind:state={row.groups_enabled}
												on:change={() => save(row, 'groups_enabled')}
											/>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	</div>
</div>
