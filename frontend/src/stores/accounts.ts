import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { accountsApi } from '@/api'
import type {
  AccountConfigItem,
  AccountListStatus,
  AccountsListParams,
  AccountsListResponse,
  AdminAccount,
} from '@/types/api'

type AccountOpResult = {
  ok: boolean
  errors: string[]
}

type RunOpOptions = {
  accountIds?: string[]
  lockKeys?: string[]
  chunkSize?: number
  request: (chunk: string[]) => Promise<{ errors?: string[] } | void>
  refreshAfter?: boolean
}

const DEFAULT_PAGE_SIZE = 50
const MATCHING_IDS_PAGE_SIZE = 200
const MATCHING_IDS_CONCURRENCY = 4
const LOCK_TIMEOUT_MS = 60000

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<AdminAccount[]>([])
  const total = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)
  const totalPages = ref(1)
  const currentQuery = ref('')
  const currentStatus = ref<AccountListStatus>('all')
  const isLoading = ref(false)
  const operatingAccounts = ref<Set<string>>(new Set())
  const batchProgress = ref<{ current: number; total: number } | null>(null)
  const latestRequestId = ref(0)

  const isOperating = computed(() => operatingAccounts.value.size > 0)

  async function loadAccounts(params: AccountsListParams = {}) {
    const nextPage = params.page ?? currentPage.value
    const nextPageSize = params.pageSize ?? pageSize.value
    const nextQuery = params.query ?? currentQuery.value
    const nextStatus = params.status ?? currentStatus.value
    const requestId = latestRequestId.value + 1
    latestRequestId.value = requestId
    isLoading.value = true

    try {
      const response = await accountsApi.list({
        page: nextPage,
        pageSize: nextPageSize,
        query: nextQuery,
        status: nextStatus,
      })

      if (requestId !== latestRequestId.value) {
        return response
      }

      accounts.value = Array.isArray(response.accounts) ? response.accounts : []
      total.value = response.total ?? accounts.value.length
      currentPage.value = response.page ?? nextPage
      pageSize.value = response.page_size ?? nextPageSize
      totalPages.value = response.total_pages ?? Math.max(1, Math.ceil(total.value / pageSize.value))
      currentQuery.value = response.query ?? nextQuery
      currentStatus.value = response.status ?? nextStatus
      return response
    } finally {
      if (requestId === latestRequestId.value) {
        isLoading.value = false
      }
    }
  }

  async function refreshAccounts() {
    return loadAccounts()
  }

  async function collectMatchingAccountIds(params: Pick<AccountsListParams, 'query' | 'status'> = {}) {
    const query = params.query ?? currentQuery.value
    const status = params.status ?? currentStatus.value
    const firstPage = await accountsApi.list({
      page: 1,
      pageSize: MATCHING_IDS_PAGE_SIZE,
      query,
      status,
    })

    const accountIds = new Set((firstPage.accounts ?? []).map((account) => account.id))
    const lastPage = Math.max(
      1,
      firstPage.total_pages ?? Math.ceil((firstPage.total ?? accountIds.size) / MATCHING_IDS_PAGE_SIZE),
    )

    for (let startPage = 2; startPage <= lastPage; startPage += MATCHING_IDS_CONCURRENCY) {
      const pageRequests: Promise<AccountsListResponse>[] = []
      const endPage = Math.min(lastPage, startPage + MATCHING_IDS_CONCURRENCY - 1)

      for (let page = startPage; page <= endPage; page += 1) {
        pageRequests.push(
          accountsApi.list({
            page,
            pageSize: MATCHING_IDS_PAGE_SIZE,
            query,
            status,
          }),
        )
      }

      const pageResponses = await Promise.all(pageRequests)
      pageResponses.forEach((response) => {
        response.accounts?.forEach((account) => accountIds.add(account.id))
      })
    }

    return Array.from(accountIds)
  }

  const addLocks = (locks: string[]) => {
    locks.forEach((lock) => operatingAccounts.value.add(lock))
  }

  const releaseLocks = (locks: string[]) => {
    locks.forEach((lock) => operatingAccounts.value.delete(lock))
  }

  const buildChunks = (ids: string[], chunkSize: number) => {
    const chunks: string[][] = []
    for (let index = 0; index < ids.length; index += chunkSize) {
      chunks.push(ids.slice(index, index + chunkSize))
    }
    return chunks
  }

  const startTimeoutGuard = (locks: string[]) => {
    if (!locks.length) return null
    return window.setTimeout(() => {
      releaseLocks(locks)
      batchProgress.value = null
    }, LOCK_TIMEOUT_MS)
  }

  async function runAccountOp(options: RunOpOptions): Promise<AccountOpResult> {
    const accountIds = options.accountIds ?? []
    const lockKeys = options.lockKeys ?? accountIds
    const chunkSize = options.chunkSize ?? 50
    const refreshAfter = options.refreshAfter ?? true

    if (!lockKeys.length && !accountIds.length) {
      return { ok: true, errors: [] }
    }

    const conflict = lockKeys.filter((id) => operatingAccounts.value.has(id))
    if (conflict.length > 0) {
      throw new Error(`${conflict.length} 个账号正在操作中`)
    }

    addLocks(lockKeys)
    const timeoutGuard = startTimeoutGuard(lockKeys)

    if (accountIds.length > 1) {
      batchProgress.value = { current: 0, total: accountIds.length }
    }

    const errors: string[] = []
    try {
      const chunks = accountIds.length ? buildChunks(accountIds, chunkSize) : [[]]
      for (const chunk of chunks) {
        const response = await options.request(chunk)
        if (response && Array.isArray(response.errors) && response.errors.length > 0) {
          errors.push(...response.errors)
        }
        if (batchProgress.value) {
          batchProgress.value.current += chunk.length
        }
      }

      if (refreshAfter) {
        await refreshAccounts()
      }

      return { ok: errors.length === 0, errors }
    } finally {
      if (timeoutGuard !== null) {
        window.clearTimeout(timeoutGuard)
      }
      releaseLocks(lockKeys)
      batchProgress.value = null
    }
  }

  async function deleteAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.delete(chunk[0])
      },
    })
  }

  async function disableAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.disable(chunk[0])
      },
    })
  }

  async function enableAccount(accountId: string) {
    return runAccountOp({
      accountIds: [accountId],
      request: async (chunk) => {
        await accountsApi.enable(chunk[0])
      },
    })
  }

  async function bulkEnable(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      chunkSize: 50,
      request: async (chunk) => accountsApi.bulkEnable(chunk),
    })
  }

  async function bulkDisable(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      chunkSize: 50,
      request: async (chunk) => accountsApi.bulkDisable(chunk),
    })
  }

  async function bulkDelete(accountIds: string[]) {
    if (!accountIds.length) return { ok: true, errors: [] }
    return runAccountOp({
      accountIds,
      chunkSize: 50,
      request: async (chunk) => accountsApi.bulkDelete(chunk),
    })
  }

  async function updateConfig(newAccounts: AccountConfigItem[]) {
    return runAccountOp({
      lockKeys: ['__config_update__'],
      request: async () => {
        await accountsApi.updateConfig(newAccounts)
      },
    })
  }

  return {
    accounts,
    total,
    currentPage,
    pageSize,
    totalPages,
    currentQuery,
    currentStatus,
    isLoading,
    isOperating,
    batchProgress,
    loadAccounts,
    refreshAccounts,
    collectMatchingAccountIds,
    deleteAccount,
    disableAccount,
    enableAccount,
    bulkEnable,
    bulkDisable,
    bulkDelete,
    updateConfig,
  }
})
