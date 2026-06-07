<script setup lang="ts">
import type { LogoProps } from '@rotki/ui-library';

defineOptions({
  inheritAttrs: false,
});

const { size, text = false, uniqueKey } = defineProps<{
  uniqueKey?: LogoProps['uniqueKey'];
  text?: LogoProps['text'];
  size?: LogoProps['size'];
}>();

const appName = 'Ryder Wealth';

// `size` matches @rotki/ui-library's RuiLogo: a height expressed in rem.
const remSize = computed<number>(() => {
  const value = Number(size);
  return Number.isFinite(value) && value > 0 ? value : 3;
});

const markStyle = computed(() => ({ height: `${get(remSize)}rem`, width: `${get(remSize)}rem` }));
const textStyle = computed(() => ({ fontSize: `${get(remSize) * 0.5}rem` }));
</script>

<template>
  <div
    v-bind="$attrs"
    :key="uniqueKey"
    class="flex items-center gap-3"
  >
    <img
      src="/assets/images/ryder-wealth-logo.svg"
      :alt="appName"
      class="shrink-0"
      :style="markStyle"
    />
    <span
      v-if="text"
      class="font-bold text-rui-text whitespace-nowrap leading-none"
      :style="textStyle"
    >
      {{ appName }}
    </span>
  </div>
</template>
