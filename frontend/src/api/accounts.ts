import apiClient from './client'
import type {
  AccountsConfigResponse,
  AccountsListParams,
  AccountsListResponse,
  AccountConfigItem,
} from '@/types/api'

export const accountsApi = {
  // 获取账户列表
  list: (params?: AccountsListParams) =>
    apiClient.get<never, AccountsListResponse>('/admin/accounts', {
      params: {
        page: params?.page,
        page_size: params?.pageSize,
        query: params?.query,
        status: params?.status,
      },
    }),

  // 获取账户配置
  getConfig: () =>
    apiClient.get<never, AccountsConfigResponse>('/admin/accounts-config'),

  // 更新账户配置
  updateConfig: (accounts: AccountConfigItem[]) =>
    apiClient.put('/admin/accounts-config', accounts),

  // 删除账户
  delete: (accountId: string) =>
    apiClient.delete(`/admin/accounts/${accountId}`),

  // 禁用账户
  disable: (accountId: string) =>
    apiClient.put(`/admin/accounts/${accountId}/disable`),

  // 启用账户
  enable: (accountId: string) =>
    apiClient.put(`/admin/accounts/${accountId}/enable`),

  // 批量启用账户（最多50个）
  bulkEnable: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-enable',
      accountIds
    ),

  // 批量禁用账户（最多50个）
  bulkDisable: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-disable',
      accountIds
    ),
  // 批量删除账户（最多50个）
  bulkDelete: (accountIds: string[]) =>
    apiClient.put<never, { status: string; success_count: number; errors: string[] }>(
      '/admin/accounts/bulk-delete',
      accountIds
    ),
}
