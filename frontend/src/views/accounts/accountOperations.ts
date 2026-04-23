import type { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { useToast } from '@/composables/useToast'
import type { useAccountsStore } from '@/stores/accounts'

type AccountStore = ReturnType<typeof useAccountsStore>
type ToastApi = ReturnType<typeof useToast>
type ConfirmDialogApi = ReturnType<typeof useConfirmDialog>
type SelectionRef = { value: Set<string> }

const formatOpErrors = (errors: string[]) => {
  if (!errors.length) return ''
  const sample = errors[0]
  return `失败 ${errors.length} 个${sample ? `，示例：${sample}` : ''}`
}

const handleOpResult = (
  toast: ToastApi,
  result: { ok: boolean; errors: string[] },
  successMessage: string,
  failMessage: string,
) => {
  if (result.ok) {
    toast.success(successMessage)
    return true
  }

  const detail = formatOpErrors(result.errors)
  toast.error(detail ? `${failMessage}，${detail}` : failMessage)
  return false
}

const removeSelectedId = (selectedIds: SelectionRef, accountId: string) => {
  if (!selectedIds.value.has(accountId)) return
  const next = new Set(selectedIds.value)
  next.delete(accountId)
  selectedIds.value = next
}

export const createAccountOperations = (
  accountsStore: AccountStore,
  toast: ToastApi,
  confirmDialog: ConfirmDialogApi,
  selectedIds: SelectionRef,
) => {
  const handleBulkEnable = async () => {
    if (!selectedIds.value.size || accountsStore.isOperating) return

    try {
      const result = await accountsStore.bulkEnable(Array.from(selectedIds.value))
      if (handleOpResult(toast, result, '批量启用成功', '批量启用失败')) {
        selectedIds.value = new Set()
      }
    } catch (error: any) {
      toast.error(error.message || '批量启用失败')
    }
  }

  const handleBulkDisable = async () => {
    if (!selectedIds.value.size || accountsStore.isOperating) return

    const confirmed = await confirmDialog.ask({
      title: '批量禁用',
      message: '确定要批量禁用选中的账号吗？',
    })
    if (!confirmed) return

    try {
      const result = await accountsStore.bulkDisable(Array.from(selectedIds.value))
      if (handleOpResult(toast, result, '批量禁用成功', '批量禁用失败')) {
        selectedIds.value = new Set()
      }
    } catch (error: any) {
      toast.error(error.message || '批量禁用失败')
    }
  }

  const handleBulkDelete = async () => {
    if (!selectedIds.value.size || accountsStore.isOperating) return

    const confirmed = await confirmDialog.ask({
      title: '批量删除',
      message: '确定要批量删除选中的账号吗？',
      confirmText: '删除',
    })
    if (!confirmed) return

    try {
      const result = await accountsStore.bulkDelete(Array.from(selectedIds.value))
      if (handleOpResult(toast, result, '批量删除成功', '批量删除失败')) {
        selectedIds.value = new Set()
      }
    } catch (error: any) {
      toast.error(error.message || '批量删除失败')
    }
  }

  const handleBatchAction = async (action: string) => {
    if (action === 'enable') {
      await handleBulkEnable()
      return
    }

    if (action === 'disable') {
      await handleBulkDisable()
      return
    }

    if (action === 'delete') {
      await handleBulkDelete()
    }
  }

  const handleEnable = async (accountId: string) => {
    if (accountsStore.isOperating) return

    try {
      const result = await accountsStore.enableAccount(accountId)
      handleOpResult(toast, result, '账号已启用', '启用失败')
    } catch (error: any) {
      toast.error(error.message || '启用失败')
    }
  }

  const handleDisable = async (accountId: string) => {
    if (accountsStore.isOperating) return

    const confirmed = await confirmDialog.ask({
      title: '禁用账号',
      message: '确定要禁用这个账号吗？',
    })
    if (!confirmed) return

    try {
      const result = await accountsStore.disableAccount(accountId)
      handleOpResult(toast, result, '账号已禁用', '禁用失败')
    } catch (error: any) {
      toast.error(error.message || '禁用失败')
    }
  }

  const handleDelete = async (accountId: string) => {
    if (accountsStore.isOperating) return

    const confirmed = await confirmDialog.ask({
      title: '删除账号',
      message: '确定要删除这个账号吗？',
      confirmText: '删除',
    })
    if (!confirmed) return

    try {
      const result = await accountsStore.deleteAccount(accountId)
      if (handleOpResult(toast, result, '账号已删除', '删除失败')) {
        removeSelectedId(selectedIds, accountId)
      }
    } catch (error: any) {
      toast.error(error.message || '删除失败')
    }
  }

  return {
    handleBulkEnable,
    handleBulkDisable,
    handleBulkDelete,
    handleBatchAction,
    handleEnable,
    handleDisable,
    handleDelete,
  }
}
