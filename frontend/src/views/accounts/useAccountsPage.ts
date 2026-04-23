import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import type { useAccountsStore } from '@/stores/accounts'
import {
  accountStatusOptions,
  type AccountStatusFilter,
} from './accountState'

type AccountStore = ReturnType<typeof useAccountsStore>
type SelectionState = 'unchecked' | 'indeterminate' | 'checked'

const ACCOUNTS_VIEW_MODE_STORAGE_KEY = 'accounts_view_mode'
const SEARCH_DEBOUNCE_MS = 250

const loadViewMode = (): 'table' | 'card' => {
  if (typeof window === 'undefined') return 'table'
  return window.localStorage.getItem(ACCOUNTS_VIEW_MODE_STORAGE_KEY) === 'card'
    ? 'card'
    : 'table'
}

const persistViewMode = (value: 'table' | 'card') => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(ACCOUNTS_VIEW_MODE_STORAGE_KEY, value)
}

export function useAccountsPage(accountsStore: AccountStore) {
  const {
    accounts,
    currentPage: storeCurrentPage,
    currentQuery: storeQuery,
    currentStatus: storeStatus,
    pageSize: storePageSize,
    total,
    totalPages,
  } = storeToRefs(accountsStore)

  const searchQuery = ref(storeQuery.value)
  const statusFilter = ref<AccountStatusFilter>(storeStatus.value as AccountStatusFilter)
  const selectedIds = ref<Set<string>>(new Set())
  const viewMode = ref<'table' | 'card'>(loadViewMode())
  const searchTimer = ref<number | null>(null)
  const isSelectingAll = ref(false)

  const pageSizeOptions = [
    { label: '20 / 页', value: 20 },
    { label: '50 / 页', value: 50 },
    { label: '100 / 页', value: 100 },
  ]

  const selectedCount = computed(() => selectedIds.value.size)
  const filteredAccounts = computed(() => ({ length: total.value }))
  const paginatedAccounts = computed(() => accounts.value)
  const currentPageIds = computed(() => paginatedAccounts.value.map((account) => account.id))
  const selectedVisibleCount = computed(() =>
    currentPageIds.value.reduce((count, accountId) => count + (selectedIds.value.has(accountId) ? 1 : 0), 0),
  )
  const currentPage = computed({
    get: () => storeCurrentPage.value,
    set: (value: number) => {
      const nextPage = Math.min(Math.max(1, value), totalPages.value)
      if (nextPage === storeCurrentPage.value) return
      void accountsStore.loadAccounts({
        page: nextPage,
        query: searchQuery.value.trim(),
        status: statusFilter.value,
      })
    },
  })
  const pageSize = computed({
    get: () => storePageSize.value,
    set: (value: number) => {
      if (value === storePageSize.value) return
      void accountsStore.loadAccounts({
        page: 1,
        pageSize: value,
        query: searchQuery.value.trim(),
        status: statusFilter.value,
      })
    },
  })
  const allSelected = computed(() =>
    currentPageIds.value.length > 0
    && selectedVisibleCount.value === currentPageIds.value.length,
  )
  const allMatchingSelected = computed(() =>
    total.value > 0
    && selectedIds.value.size === total.value
    && allSelected.value,
  )
  const selectionState = computed<SelectionState>(() => {
    if (allMatchingSelected.value) return 'checked'
    if (selectedIds.value.size > 0) return 'indeterminate'
    return 'unchecked'
  })
  const selectionHint = computed(() => {
    if (isSelectingAll.value) {
      return `正在选中全部 ${total.value} 个匹配账号...`
    }
    if (selectionState.value === 'checked') {
      return `已选全部 ${selectedCount.value} 个匹配账号`
    }
    if (allSelected.value && total.value > selectedIds.value.size) {
      return `已选当前页 ${selectedVisibleCount.value} 个，再点一次全选全部 ${total.value} 个`
    }
    if (selectedIds.value.size > 0) {
      return `已选 ${selectedCount.value} 个账号`
    }
    return ''
  })

  const loadAccounts = async (overrides?: {
    page?: number
    pageSize?: number
    query?: string
    status?: AccountStatusFilter
  }) => accountsStore.loadAccounts({
    page: overrides?.page ?? storeCurrentPage.value,
    pageSize: overrides?.pageSize ?? storePageSize.value,
    query: overrides?.query ?? searchQuery.value.trim(),
    status: overrides?.status ?? statusFilter.value,
  })

  watch(viewMode, (value) => {
    persistViewMode(value)
  })

  watch(statusFilter, (value) => {
    clearSelection()
    void loadAccounts({ page: 1, status: value })
  })

  watch(searchQuery, (value) => {
    if (searchTimer.value !== null) {
      window.clearTimeout(searchTimer.value)
    }
    searchTimer.value = window.setTimeout(() => {
      clearSelection()
      void loadAccounts({ page: 1, query: value.trim() })
    }, SEARCH_DEBOUNCE_MS)
  })

  onBeforeUnmount(() => {
    if (searchTimer.value !== null) {
      window.clearTimeout(searchTimer.value)
    }
  })

  const toggleSelect = (accountId: string, checked?: boolean) => {
    const next = new Set(selectedIds.value)
    const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(accountId)
    if (shouldSelect) {
      next.add(accountId)
    } else {
      next.delete(accountId)
    }
    selectedIds.value = next
  }

  const selectCurrentPage = () => {
    const next = new Set(selectedIds.value)
    currentPageIds.value.forEach((accountId) => next.add(accountId))
    selectedIds.value = next
  }

  const selectAllMatching = async () => {
    if (isSelectingAll.value) return
    isSelectingAll.value = true
    try {
      const accountIds = await accountsStore.collectMatchingAccountIds({
        query: searchQuery.value.trim(),
        status: statusFilter.value,
      })
      selectedIds.value = new Set(accountIds)
    } finally {
      isSelectingAll.value = false
    }
  }

  const toggleSelectAll = async () => {
    if (!currentPageIds.value.length) return

    if (selectionState.value === 'checked') {
      clearSelection()
      return
    }

    if (allSelected.value && total.value > selectedIds.value.size) {
      await selectAllMatching()
      return
    }

    selectCurrentPage()
  }

  const clearSelection = () => {
    selectedIds.value = new Set()
  }

  const refreshAccounts = async () => {
    await loadAccounts()
    clearSelection()
  }

  return {
    searchQuery,
    statusFilter,
    statusOptions: accountStatusOptions,
    selectedIds,
    viewMode,
    currentPage,
    pageSize,
    pageSizeOptions,
    selectedCount,
    filteredAccounts,
    paginatedAccounts,
    totalPages,
    allSelected,
    allMatchingSelected,
    isSelectingAll,
    selectionHint,
    selectionState,
    refreshAccounts,
    toggleSelect,
    toggleSelectAll,
    clearSelection,
  }
}
