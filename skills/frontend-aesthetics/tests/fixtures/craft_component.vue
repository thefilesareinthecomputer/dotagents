<template>
  <nav class="flex gap-4">
    <a class="px-3 py-2 transition-all duration-200" href="/docs">Docs</a>
    <button class="rounded md:focus:outline-none" type="button">{{ label }}</button>
  </nav>
</template>

<script setup>
const label = "Menu";
</script>

<style scoped>
/* Findings in this block must report lines of the whole file, not the block. */
.nav-link {
  transition: color 150ms ease;
}

.menu-button:focus {
  outline: 0;
}

.loader {
  animation: pulse 2s ease-in-out infinite;
}
</style>

<style lang="scss">
.not-parsed { transition: all 1s; }
</style>
