<script>
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');
</script>

<div class="max-w-3xl">
	<h1 class="text-2xl font-bold text-gray-900 dark:text-white">{$i18n.t('Tokens')}</h1>
</div>
