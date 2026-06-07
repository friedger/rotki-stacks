<script setup lang="ts">
import WalletImportSelection from '@/modules/accounts/blockchain/WalletImportSelection.vue';
import { getErrorMessage } from '@/modules/core/common/logging/error-handling';
import { useMessageStore } from '@/modules/core/common/use-message-store';
import { useInterop } from '@/modules/shell/app/use-electron-interop';

const props = defineProps<{
  disabled: boolean;
  // Show the browser-wallet / MetaMask import (EVM chains).
  metamask?: boolean;
  // If set (e.g. 'STX', 'BTC', 'ETH', 'SOL'), show the "Import from Ryder One" button and pick
  // the account matching this symbol from the device.
  ryderSymbol?: string;
}>();

const emit = defineEmits<{
  'update:addresses': [addresses: string[]];
}>();

const { t } = useI18n({ useScope: 'global' });

const [DefineButton, ReuseButton] = createReusableTemplate<{ buttonDisabled?: boolean; onClick?: () => void }>();
const { importFromRyder, isPackaged, metamaskImport } = useInterop();
const { setMessage } = useMessageStore();

const ryderLoading = ref<boolean>(false);

async function importAddresses() {
  try {
    const addresses = await metamaskImport();
    emit('update:addresses', addresses);
  }
  catch (error: unknown) {
    setMessage({
      description: getErrorMessage(error),
      success: false,
      title: t('input_mode_select.import_from_wallet.label'),
    });
  }
}

async function importRyder() {
  const symbol = props.ryderSymbol;
  if (!symbol)
    return;

  set(ryderLoading, true);
  try {
    const accounts = await importFromRyder();
    const match = accounts.find(account => account.symbol === symbol);
    if (!match)
      throw new Error(t('input_mode_select.import_from_ryder.no_account', { symbol }));

    emit('update:addresses', [match.address]);
  }
  catch (error: any) {
    setMessage({
      description: error.message,
      success: false,
      title: t('input_mode_select.import_from_ryder.label'),
    });
  }
  finally {
    set(ryderLoading, false);
  }
}
</script>

<template>
  <DefineButton #default="{ buttonDisabled, onClick }">
    <RuiTooltip :disabled="disabled">
      <template #activator>
        <RuiButton
          variant="outlined"
          color="primary"
          class="min-h-[3.5rem] relative"
          :class="{ 'opacity-50': buttonDisabled || disabled }"
          :disabled="buttonDisabled || disabled"
          @click="onClick?.()"
        >
          <RuiIcon name="lu-wallet-minimal" />
          <template #append>
            <div class="absolute w-4 h-4 bg-current rounded-full text-primary right-2 bottom-2 flex items-center justify-center">
              <RuiIcon
                name="lu-download"
                class="text-white"
                size="10"
              />
            </div>
          </template>
        </RuiButton>
      </template>
      {{ t('input_mode_select.import_from_wallet.label') }}
    </RuiTooltip>
  </DefineButton>

  <template v-if="metamask">
    <ReuseButton
      v-if="isPackaged"
      :on-click="importAddresses"
    />

    <WalletImportSelection
      v-else
      @import-addresses="emit('update:addresses', $event)"
    >
      <template #default="{ attrs }">
        <ReuseButton v-bind="attrs" />
      </template>
    </WalletImportSelection>
  </template>

  <RuiTooltip
    v-if="isPackaged && ryderSymbol"
    :disabled="disabled"
  >
    <template #activator>
      <RuiButton
        variant="outlined"
        color="primary"
        class="min-h-[3.5rem] relative"
        :class="{ 'opacity-50': disabled }"
        :disabled="disabled"
        :loading="ryderLoading"
        @click="importRyder()"
      >
        <RuiIcon name="lu-key-round" />
        <template #append>
          <div class="absolute w-4 h-4 bg-current rounded-full text-primary right-2 bottom-2 flex items-center justify-center">
            <RuiIcon
              name="lu-download"
              class="text-white"
              size="10"
            />
          </div>
        </template>
      </RuiButton>
    </template>
    {{ t('input_mode_select.import_from_ryder.label') }}
  </RuiTooltip>
</template>
