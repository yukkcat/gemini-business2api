import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { statsApi } from '@/api'
import {
  chartColors,
  createLineSeries,
  createModelLegendConfig,
  filterValidModels,
  createPieDataItem,
  getLineChartTheme,
  getModelColor,
  getPieChartTheme,
} from '@/lib/chartTheme'


export function useDashboardPage() {
  type ChartInstance = {
    setOption: (
      option: unknown,
      opts?: boolean | { notMerge?: boolean; lazyUpdate?: boolean; replaceMerge?: string[] }
    ) => void
    resize: () => void
    dispose: () => void
    clear?: () => void
    off?: (eventName: string) => void
    on?: (eventName: string, handler: (params: any) => void) => void
    dispatchAction?: (payload: Record<string, unknown>) => void
  }
  type RenderMode = 'initial' | 'range' | 'refresh'
  type ChartType = 'hourlyRequests' | 'trend' | 'successRate' | 'model' | 'modelRank' | 'responseTime'
  type OverviewPayload = Record<string, any>

  type TimeRange = '24h' | '7d' | '30d'
  type DashboardRangesState = Record<ChartType, TimeRange>

  const DASHBOARD_RANGES_STORAGE_KEY = 'dashboard:chart-ranges:v1'
  const DASHBOARD_AUTO_REFRESH_MS = 15000

  // 时间范围选择
  const timeRanges = [
    { label: '24小时', value: '24h' },
    { label: '7天', value: '7d' },
    { label: '30天', value: '30d' },
  ] as const

  const validRangeSet = new Set<TimeRange>(['24h', '7d', '30d'])

  function sanitizeTimeRange(value: unknown, fallback: TimeRange = '24h'): TimeRange {
    const raw = String(value || '').trim() as TimeRange
    return validRangeSet.has(raw) ? raw : fallback
  }

  function loadStoredRanges(): Partial<DashboardRangesState> {
    if (typeof window === 'undefined') return {}
    try {
      const raw = window.localStorage.getItem(DASHBOARD_RANGES_STORAGE_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Partial<Record<ChartType, unknown>>
      return {
        hourlyRequests: sanitizeTimeRange(parsed.hourlyRequests),
        trend: sanitizeTimeRange(parsed.trend),
        successRate: sanitizeTimeRange(parsed.successRate),
        model: sanitizeTimeRange(parsed.model),
        modelRank: sanitizeTimeRange(parsed.modelRank),
        responseTime: sanitizeTimeRange(parsed.responseTime),
      }
    } catch {
      return {}
    }
  }

  const storedRanges = loadStoredRanges()

  // 每个图表独立的时间范围
  const timeRangeHourlyRequests = ref<TimeRange>(sanitizeTimeRange(storedRanges.hourlyRequests))
  const timeRangeTrend = ref<TimeRange>(sanitizeTimeRange(storedRanges.trend))
  const timeRangeSuccessRate = ref<TimeRange>(sanitizeTimeRange(storedRanges.successRate))
  const timeRangeModel = ref<TimeRange>(sanitizeTimeRange(storedRanges.model))
  const timeRangeModelRank = ref<TimeRange>(sanitizeTimeRange(storedRanges.modelRank))
  const timeRangeResponseTime = ref<TimeRange>(sanitizeTimeRange(storedRanges.responseTime))

  function persistRanges() {
    if (typeof window === 'undefined') return
    const ranges: DashboardRangesState = {
      hourlyRequests: sanitizeTimeRange(timeRangeHourlyRequests.value),
      trend: sanitizeTimeRange(timeRangeTrend.value),
      successRate: sanitizeTimeRange(timeRangeSuccessRate.value),
      model: sanitizeTimeRange(timeRangeModel.value),
      modelRank: sanitizeTimeRange(timeRangeModelRank.value),
      responseTime: sanitizeTimeRange(timeRangeResponseTime.value),
    }
    try {
      window.localStorage.setItem(DASHBOARD_RANGES_STORAGE_KEY, JSON.stringify(ranges))
    } catch {
      // ignore localStorage write errors
    }
  }

  // 创建图表监听器的工厂函数
  function createChartWatcher(chartType: ChartType, updateFn: (mode?: RenderMode) => void) {
    return async (newVal: TimeRange) => {
      persistRanges()
      await loadChartData(chartType, newVal)
      updateFn('range')
    }
  }

  // 监听各图表时间范围变化 - 只更新对应图表
  watch(timeRangeHourlyRequests, createChartWatcher('hourlyRequests', updateHourlyRequestsChart))
  watch(timeRangeTrend, createChartWatcher('trend', updateTrendChart))
  watch(timeRangeSuccessRate, createChartWatcher('successRate', updateSuccessRateChart))
  watch(timeRangeModel, createChartWatcher('model', updateModelChart))
  watch(timeRangeModelRank, createChartWatcher('modelRank', updateModelRankChart))
  watch(timeRangeResponseTime, createChartWatcher('responseTime', updateResponseTimeChart))

  const stats = ref([
    {
      label: '账号总数',
      value: '0',
      caption: '账号池中的总数量',
      icon: 'lucide:database',
      iconBg: 'bg-sky-100',
      iconColor: 'text-sky-600'
    },
    {
      label: '活跃账号',
      value: '0',
      caption: '正常运行中，可随时调用',
      icon: 'lucide:check-circle',
      iconBg: 'bg-emerald-100',
      iconColor: 'text-emerald-600'
    },
    {
      label: '失败账号',
      value: '0',
      caption: '已禁用或过期，需要处理',
      icon: 'lucide:alert-circle',
      iconBg: 'bg-red-100',
      iconColor: 'text-red-600'
    },
    {
      label: '限流账号',
      value: '0',
      caption: '触发限流，正在冷却中',
      icon: 'lucide:clock',
      iconBg: 'bg-amber-100',
      iconColor: 'text-amber-600'
    },
  ])

  // 每个图表独立的数据状态
  const chartData = ref({
    hourlyRequests: {
      labels: [] as string[],
      modelRequests: {} as Record<string, number[]>,
    },
    trend: {
      labels: [] as string[],
      totalRequests: [] as number[],
      failedRequests: [] as number[],
      rateLimitedRequests: [] as number[],
      successRequests: [] as number[],
    },
    successRate: {
      labels: [] as string[],
      totalRequests: [] as number[],
      failedRequests: [] as number[],
    },
    model: {
      modelRequests: {} as Record<string, number[]>,
    },
    modelRank: {
      modelRequests: {} as Record<string, number[]>,
    },
    responseTime: {
      labels: [] as string[],
      modelTtfbTimes: {} as Record<string, number[]>,
      modelTotalTimes: {} as Record<string, number[]>,
    },
  })

  const overviewCache = new Map<string, OverviewPayload>()
  const overviewRequests = new Map<string, Promise<OverviewPayload>>()

  const trendChartRef = ref<HTMLDivElement | null>(null)
  const modelChartRef = ref<HTMLDivElement | null>(null)
  const successRateChartRef = ref<HTMLDivElement | null>(null)
  const hourlyRequestsChartRef = ref<HTMLDivElement | null>(null)
  const modelRankChartRef = ref<HTMLDivElement | null>(null)
  const responseTimeChartRef = ref<HTMLDivElement | null>(null)

  const charts = {
    trend: null as ChartInstance | null,
    model: null as ChartInstance | null,
    successRate: null as ChartInstance | null,
    hourlyRequests: null as ChartInstance | null,
    modelRank: null as ChartInstance | null,
    responseTime: null as ChartInstance | null,
  }

  type ChartKey = keyof typeof charts
  const renderProfiles: Record<RenderMode, {
    duration: number
    updateDuration: number
    delayStep: number
    lazyUpdate: boolean
  }> = {
    initial: { duration: 860, updateDuration: 620, delayStep: 14, lazyUpdate: false },
    range: { duration: 560, updateDuration: 460, delayStep: 8, lazyUpdate: false },
    refresh: { duration: 260, updateDuration: 220, delayStep: 0, lazyUpdate: true },
  }
  const chartFirstRenderState = ref<Record<ChartKey, boolean>>({
    trend: true,
    model: true,
    successRate: true,
    hourlyRequests: true,
    modelRank: true,
    responseTime: true,
  })
  const chartsBootstrapped = ref(false)
  const dashboardDataReady = ref(false)
  let chartBootstrapTimer: number | null = null
  let dashboardRefreshTimer: number | null = null
  const modelLayoutIsMobile = ref<boolean | null>(null)

  function bindResizeListener() {
    window.removeEventListener('resize', handleResize)
    window.addEventListener('resize', handleResize)
  }

  function unbindResizeListener() {
    window.removeEventListener('resize', handleResize)
  }

  function applyAnimatedOption(key: ChartKey, option: Record<string, unknown>, mode: RenderMode = 'refresh') {
    const chart = charts[key]
    if (!chart) return
    const isFirstRender = chartFirstRenderState.value[key]
    const activeMode: RenderMode = isFirstRender ? 'initial' : mode
    const profile = renderProfiles[activeMode]
    const optionWithAnimation = {
      ...option,
      animation: true,
      animationDuration: profile.duration,
      animationDurationUpdate: profile.updateDuration,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      animationDelay: profile.delayStep > 0 ? (idx: number) => Math.min(idx * profile.delayStep, 180) : 0,
      animationDelayUpdate: profile.delayStep > 0 ? (idx: number) => Math.min(idx * Math.max(4, Math.floor(profile.delayStep / 2)), 120) : 0,
    }
    chart.setOption(optionWithAnimation, {
      notMerge: false,
      lazyUpdate: profile.lazyUpdate,
    })
    chartFirstRenderState.value[key] = false
  }

  function initChart(
    ref: HTMLDivElement | null,
    key: ChartKey,
    updateFn: (mode?: RenderMode) => void
  ): boolean {
    const echarts = (window as any).echarts as { init: (el: HTMLElement) => ChartInstance } | undefined
    if (!echarts || !ref) return false
    if (charts[key]) return true
    charts[key] = echarts.init(ref)
    updateFn('initial')
    return true
  }

  function bootstrapCharts() {
    if (chartsBootstrapped.value) return
    const readyStates = [
      initChart(trendChartRef.value, 'trend', updateTrendChart),
      initChart(modelChartRef.value, 'model', updateModelChart),
      initChart(successRateChartRef.value, 'successRate', updateSuccessRateChart),
      initChart(hourlyRequestsChartRef.value, 'hourlyRequests', updateHourlyRequestsChart),
      initChart(modelRankChartRef.value, 'modelRank', updateModelRankChart),
      initChart(responseTimeChartRef.value, 'responseTime', updateResponseTimeChart),
    ]
    chartsBootstrapped.value = readyStates.every(Boolean)

    if (!chartsBootstrapped.value) {
      scheduleChartBootstrap(160)
    }
  }

  function scheduleChartBootstrap(delayMs = 80) {
    if (chartsBootstrapped.value) return
    if (chartBootstrapTimer) window.clearTimeout(chartBootstrapTimer)
    chartBootstrapTimer = window.setTimeout(() => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          bootstrapCharts()
        })
      })
    }, delayMs)
  }

  function replayChartIntro() {
    if (!chartsBootstrapped.value) return
    ;(Object.keys(charts) as ChartKey[]).forEach((key) => {
      chartFirstRenderState.value[key] = true
      charts[key]?.clear?.()
    })
    updateTrendChart('initial')
    updateModelChart('initial')
    updateSuccessRateChart('initial')
    updateHourlyRequestsChart('initial')
    updateModelRankChart('initial')
    updateResponseTimeChart('initial')
  }

  onMounted(async () => {
    await refreshDashboardData({ force: true })

    scheduleChartBootstrap()
    bindResizeListener()
    startDashboardAutoRefresh()
  })

  onActivated(() => {
    bindResizeListener()
    startDashboardAutoRefresh()
    if (!dashboardDataReady.value) {
      void refreshDashboardData({ force: true })
      return
    }
    if (chartsBootstrapped.value) {
      requestAnimationFrame(() => {
        handleResize()
        replayChartIntro()
      })
    } else {
      scheduleChartBootstrap(0)
    }
    void refreshDashboardData({ force: true, syncCharts: true })
  })

  onDeactivated(() => {
    unbindResizeListener()
    stopDashboardAutoRefresh()
    if (chartBootstrapTimer) {
      window.clearTimeout(chartBootstrapTimer)
      chartBootstrapTimer = null
    }
  })

  onBeforeUnmount(() => {
    unbindResizeListener()
    stopDashboardAutoRefresh()
    if (chartBootstrapTimer) window.clearTimeout(chartBootstrapTimer)
    Object.values(charts).forEach(chart => chart?.dispose())
  })

  function updateTrendChart(mode: RenderMode = 'refresh') {
    if (!charts.trend) return

    const theme = getLineChartTheme()

    applyAnimatedOption('trend', {
      ...theme,
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.trend.labels,
      },
      series: [
        createLineSeries('成功(总请求)', chartData.value.trend.successRequests, chartColors.primary, {
          areaOpacity: 0.25,
          zIndex: 1,
        }),
        createLineSeries('失败', chartData.value.trend.failedRequests, chartColors.danger, {
          areaOpacity: 0.3,
          zIndex: 2,
        }),
        createLineSeries('限流', chartData.value.trend.rateLimitedRequests, chartColors.warning, {
          areaOpacity: 0.3,
          zIndex: 2,
        }),
      ],
    }, mode)
  }

  function getModelTotals() {
    return Object.entries(chartData.value.model.modelRequests)
      .map(([model, data]) => ({
        model,
        data: createPieDataItem(model, data.reduce((sum, item) => sum + item, 0), getModelColor(model)),
        total: data.reduce((sum, item) => sum + item, 0),
      }))
      .filter(item => item.total > 0)
  }

  function updateModelChart(mode: RenderMode = 'refresh') {
    if (!charts.model) return

    const isMobile = window.innerWidth < 768
    modelLayoutIsMobile.value = isMobile
    const theme = getPieChartTheme(isMobile)
    const modelData = getModelTotals().map(item => item.data)

    applyAnimatedOption('model', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        formatter: (params: { name: string; value: number; percent: number }) =>
          `${params.name}: ${params.value} 次 (${params.percent}%)`,
      },
      legend: {
        ...theme.legend,
        ...createModelLegendConfig(modelData.map(item => item.name)),
      },
      series: [
        {
          ...theme.series,
          center: ['50%', '50%'],
          data: modelData,
        },
      ],
    }, mode)
  }

  function handleResize() {
    Object.entries(charts).forEach(([key, chart]) => {
      if (chart) {
        if (key === 'model') {
          const nowMobile = window.innerWidth < 768
          if (modelLayoutIsMobile.value !== nowMobile) {
            updateModelChart()
          } else {
            chart.resize()
          }
        } else {
          chart.resize()
        }
      }
    })
  }

  function getChartRange(chartType: ChartType): TimeRange {
    switch (chartType) {
      case 'hourlyRequests':
        return sanitizeTimeRange(timeRangeHourlyRequests.value)
      case 'trend':
        return sanitizeTimeRange(timeRangeTrend.value)
      case 'successRate':
        return sanitizeTimeRange(timeRangeSuccessRate.value)
      case 'model':
        return sanitizeTimeRange(timeRangeModel.value)
      case 'modelRank':
        return sanitizeTimeRange(timeRangeModelRank.value)
      case 'responseTime':
        return sanitizeTimeRange(timeRangeResponseTime.value)
    }
  }

  function getActiveRanges() {
    return Array.from(
      new Set<string>([
        '24h',
        timeRangeHourlyRequests.value,
        timeRangeTrend.value,
        timeRangeSuccessRate.value,
        timeRangeModel.value,
        timeRangeModelRank.value,
        timeRangeResponseTime.value,
      ]),
    )
  }

  function stopDashboardAutoRefresh() {
    if (dashboardRefreshTimer !== null) {
      window.clearInterval(dashboardRefreshTimer)
      dashboardRefreshTimer = null
    }
  }

  function startDashboardAutoRefresh() {
    stopDashboardAutoRefresh()
    dashboardRefreshTimer = window.setInterval(() => {
      void refreshDashboardData({ force: true, syncCharts: true })
    }, DASHBOARD_AUTO_REFRESH_MS)
  }

  async function getOverview(timeRange: string, options: { force?: boolean } = {}) {
    if (options.force) {
      overviewCache.delete(timeRange)
    }

    const cached = overviewCache.get(timeRange)
    if (cached) return cached

    const inflight = overviewRequests.get(timeRange)
    if (inflight) return inflight

    const request = statsApi
      .overview(timeRange)
      .then((overview) => {
        const payload = overview as OverviewPayload
        overviewCache.set(timeRange, payload)
        return payload
      })
      .finally(() => {
        overviewRequests.delete(timeRange)
      })

    overviewRequests.set(timeRange, request)
    return request
  }

  function applyAccountStats(overview: OverviewPayload) {
    stats.value[0].value = (overview.total_accounts ?? 0).toString()
    stats.value[1].value = (overview.active_accounts ?? 0).toString()
    stats.value[2].value = (overview.failed_accounts ?? 0).toString()
    stats.value[3].value = (overview.rate_limited_accounts ?? 0).toString()
  }

  function getTrendPayload(overview: OverviewPayload) {
    return overview.trend || {
      labels: [],
      total_requests: [],
      failed_requests: [],
      rate_limited_requests: [],
      model_requests: {},
      model_ttfb_times: {},
      model_total_times: {},
    }
  }

  function applyOverviewToChartData(chartType: ChartType, overview: OverviewPayload) {
    const trend = getTrendPayload(overview)
    const failed = trend.failed_requests || []
    const limited = trend.rate_limited_requests || []
    const failureSeries = (trend.total_requests || []).map((_: number, idx: number) => (failed[idx] || 0) + (limited[idx] || 0))
    const successSeries = (trend.total_requests || []).map((item: number) => Math.max(item, 0))

    switch (chartType) {
      case 'hourlyRequests':
        chartData.value.hourlyRequests.labels = trend.labels || []
        chartData.value.hourlyRequests.modelRequests = filterValidModels(trend.model_requests || {})
        break
      case 'trend':
        chartData.value.trend.labels = trend.labels || []
        chartData.value.trend.totalRequests = trend.total_requests || []
        chartData.value.trend.failedRequests = failed
        chartData.value.trend.rateLimitedRequests = limited
        chartData.value.trend.successRequests = successSeries
        break
      case 'successRate':
        chartData.value.successRate.labels = trend.labels || []
        chartData.value.successRate.totalRequests = trend.total_requests || []
        chartData.value.successRate.failedRequests = failureSeries
        break
      case 'model':
        chartData.value.model.modelRequests = filterValidModels(trend.model_requests || {})
        break
      case 'modelRank':
        chartData.value.modelRank.modelRequests = filterValidModels(trend.model_requests || {})
        break
      case 'responseTime':
        chartData.value.responseTime.labels = trend.labels || []
        chartData.value.responseTime.modelTtfbTimes = filterValidModels(trend.model_ttfb_times || {})
        chartData.value.responseTime.modelTotalTimes = filterValidModels(trend.model_total_times || {})
        break
    }
  }

  function refreshRenderedCharts(mode: RenderMode = 'refresh') {
    updateHourlyRequestsChart(mode)
    updateTrendChart(mode)
    updateSuccessRateChart(mode)
    updateModelChart(mode)
    updateModelRankChart(mode)
    updateResponseTimeChart(mode)
  }

  async function refreshDashboardData(
    options: {
      force?: boolean
      syncCharts?: boolean
    } = {},
  ) {
    try {
      const activeRanges = getActiveRanges()

      await Promise.all(
        activeRanges.map((timeRange) => getOverview(timeRange, { force: options.force })),
      )

      const accountOverview = overviewCache.get('24h')
      if (accountOverview) {
        applyAccountStats(accountOverview)
      }

      ;(['hourlyRequests', 'trend', 'successRate', 'model', 'modelRank', 'responseTime'] as ChartType[]).forEach((chartType) => {
        const overview = overviewCache.get(getChartRange(chartType))
        if (overview) applyOverviewToChartData(chartType, overview)
      })

      if (options.syncCharts && chartsBootstrapped.value) {
        refreshRenderedCharts()
      }
    } catch (error) {
      console.error('Failed to refresh dashboard data:', error)
    } finally {
      dashboardDataReady.value = true
    }
  }

  async function loadChartData(chartType: ChartType, timeRange: string) {
    try {
      const overview = await getOverview(timeRange)
      applyOverviewToChartData(chartType, overview)
    } catch (error) {
      console.error(`Failed to load ${chartType} data:`, error)
    }
  }

  function updateSuccessRateChart(mode: RenderMode = 'refresh') {
    if (!charts.successRate) return

    const theme = getLineChartTheme()
    const successRates = chartData.value.successRate.totalRequests.map((total, idx) => {
      const failure = chartData.value.successRate.failedRequests[idx] || 0
      return total > 0 ? Math.round(((total - failure) / total) * 100) : 100
    })

    applyAnimatedOption('successRate', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          const param = params[0]
          return `<div style="font-weight: 600; margin-bottom: 4px;">${param.axisValue}</div>
            <div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
              <span>${param.marker} ${param.seriesName}</span>
              <span style="font-weight: 600;">${param.value}%</span>
            </div>`
        },
      },
      grid: {
        ...theme.grid,
        top: 32,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.successRate.labels,
      },
      yAxis: {
        ...theme.yAxis,
        max: 100,
        axisLabel: {
          ...theme.yAxis.axisLabel,
          formatter: '{value}%',
        },
      },
      series: [
        {
          name: '成功率',
          type: 'line',
          data: successRates,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            width: 3,
          },
          areaStyle: {
            opacity: 0.3,
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: chartColors.success },
                { offset: 1, color: 'rgba(16, 185, 129, 0.1)' },
              ],
            },
          },
          itemStyle: {
            color: chartColors.success,
          },
        },
      ],
    }, mode)
  }

  function updateHourlyRequestsChart(mode: RenderMode = 'refresh') {
    if (!charts.hourlyRequests) return

    const theme = getLineChartTheme()
    const modelNames = Object.keys(chartData.value.hourlyRequests.modelRequests)

    if (modelNames.length === 0) {
      applyAnimatedOption('hourlyRequests', {
        ...theme,
        grid: {
          ...theme.grid,
          left: 34,
          right: 24,
          top: 32,
          bottom: 32,
        },
        xAxis: {
          ...theme.xAxis,
          data: chartData.value.hourlyRequests.labels,
          boundaryGap: true,
        },
        yAxis: {
          ...theme.yAxis,
        },
        series: [
          {
            name: '总请求',
            type: 'bar',
            data: [],
            barWidth: '60%',
            itemStyle: {
              color: chartColors.primary,
              borderRadius: [4, 4, 0, 0],
            },
          },
        ],
      }, mode)
      return
    }

    const pointCount = chartData.value.hourlyRequests.labels.length
    const topSeriesIndexByPoint = Array.from({ length: pointCount }, (_, pointIndex) => {
      for (let seriesIndex = modelNames.length - 1; seriesIndex >= 0; seriesIndex -= 1) {
        const value = Number(chartData.value.hourlyRequests.modelRequests[modelNames[seriesIndex]]?.[pointIndex] || 0)
        if (value > 0) return seriesIndex
      }
      return -1
    })

    const series = modelNames.map((modelName, seriesIndex) => ({
      name: modelName,
      type: 'bar',
      stack: 'total',
      data: (chartData.value.hourlyRequests.modelRequests[modelName] || []).map((value, pointIndex) => ({
        value,
        itemStyle: {
          color: getModelColor(modelName),
          borderRadius: topSeriesIndexByPoint[pointIndex] === seriesIndex ? [4, 4, 0, 0] : [0, 0, 0, 0],
        },
      })),
    }))

    applyAnimatedOption('hourlyRequests', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          let result = `<div style="font-weight: 600; margin-bottom: 4px;">${params[0].axisValue}</div>`
          let total = 0
          params.forEach((item: any) => {
            total += item.value || 0
            result += `<div style="display: flex; justify-content: space-between; gap: 16px; align-items: center;">
              <span>${item.marker} ${item.seriesName}</span>
              <span style="font-weight: 600;">${item.value || 0}</span>
            </div>`
          })
          result += `<div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #e5e5e5; font-weight: 600;">
            总计: ${total}
          </div>`
          return result
        },
      },
      legend: {
        ...theme.legend,
        ...createModelLegendConfig(modelNames),
        top: 0,
        right: 0,
        type: 'scroll',
        pageIconSize: 10,
        pageTextStyle: {
          fontSize: 10,
        },
      },
      grid: {
        ...theme.grid,
        left: 34,
        right: 24,
        top: modelNames.length > 5 ? 56 : 48,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.hourlyRequests.labels,
        boundaryGap: true,
      },
      yAxis: {
        ...theme.yAxis,
      },
      series: series,
    }, mode)

  }

  function updateModelRankChart(mode: RenderMode = 'refresh') {
    if (!charts.modelRank) return

    const theme = getLineChartTheme()
    const modelTotals = Object.entries(chartData.value.modelRank.modelRequests)
      .map(([model, data]) => ({
        model,
        total: data.reduce((sum, item) => sum + item, 0),
      }))
      .filter(item => item.total > 0)
      .sort((a, b) => b.total - a.total)

    const modelNames = modelTotals.map(item => item.model)
    const modelValues = modelTotals.map(item => item.total)
    const modelColors = modelNames.map(name => getModelColor(name))

    applyAnimatedOption('modelRank', {
      ...theme,
      grid: {
        left: 12,
        right: 60,
        top: 16,
        bottom: 16,
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          ...theme.xAxis.axisLabel,
          fontSize: 10,
        },
        splitLine: {
          lineStyle: {
            color: '#e5e5e5',
            type: 'solid',
          },
        },
      },
      yAxis: {
        type: 'category',
        data: modelNames,
        axisLine: {
          show: false,
        },
        axisTick: {
          show: false,
        },
        axisLabel: {
          ...theme.yAxis.axisLabel,
          fontSize: 11,
        },
      },
      series: [
        {
          type: 'bar',
          data: modelValues.map((value, idx) => ({
            value,
            itemStyle: {
              color: modelColors[idx],
              borderRadius: [0, 4, 4, 0],
            },
          })),
          barWidth: '50%',
          label: {
            show: true,
            position: 'right',
            fontSize: 11,
            color: '#6b6b6b',
            formatter: '{c}',
          },
        },
      ],
    }, mode)
  }

  function updateResponseTimeChart(mode: RenderMode = 'refresh') {
    if (!charts.responseTime) return

    const theme = getLineChartTheme()
    const modelNames = Object.keys(chartData.value.responseTime.modelTtfbTimes)

    if (modelNames.length === 0) {
      applyAnimatedOption('responseTime', {
        ...theme,
        grid: {
          ...theme.grid,
          top: 32,
          bottom: 32,
        },
        xAxis: {
          ...theme.xAxis,
          data: chartData.value.responseTime.labels,
        },
        yAxis: {
          ...theme.yAxis,
          axisLabel: {
            ...theme.yAxis.axisLabel,
            formatter: '{value}s',
          },
        },
        series: [],
      }, mode)
      return
    }

    // 构建系列：每个模型两条线（完成实线 + 首响虚线）
    const series: any[] = []
    const legendData: string[] = []

    modelNames.forEach((modelName) => {
      const color = getModelColor(modelName)
      legendData.push(modelName)

      // 将毫秒转换为秒
      const ttfbInSeconds = chartData.value.responseTime.modelTtfbTimes[modelName].map((ms: number) => Number((ms / 1000).toFixed(2)))
      const totalInSeconds = chartData.value.responseTime.modelTotalTimes[modelName].map((ms: number) => Number((ms / 1000).toFixed(2)))

      // 完成时间 - 实线（主线，显示在图例中）
      series.push(
        createLineSeries(modelName, totalInSeconds, color, {
          smooth: true,
          areaOpacity: 0.15,
          zIndex: 2,
        })
      )

      // 首响时间 - 虚线（不显示在图例中，但跟随主线的显示状态）
      const ttfbSeries = createLineSeries(modelName, ttfbInSeconds, color, {
        smooth: true,
        areaOpacity: 0,
        zIndex: 1,
        lineStyle: {
          type: 'dashed',
          width: 2,
        },
      })
      // 修改name以区分，但使用相同的legendName来关联
      ttfbSeries.name = `${modelName}-ttfb`
      series.push(ttfbSeries)
    })

    applyAnimatedOption('responseTime', {
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'axis',
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          let result = `<div style="font-weight: 600; margin-bottom: 4px;">${params[0].axisValue}</div>`

          // 按模型分组显示
          const modelMap = new Map<string, { total?: number, ttfb?: number, color?: string }>()
          params.forEach((item: any) => {
            const seriesName = item.seriesName
            if (seriesName.endsWith('-ttfb')) {
              const modelName = seriesName.replace('-ttfb', '')
              const data = modelMap.get(modelName) || {}
              data.ttfb = item.value
              data.color = item.color
              modelMap.set(modelName, data)
            } else {
              const data = modelMap.get(seriesName) || {}
              data.total = item.value
              data.color = item.color
              modelMap.set(seriesName, data)
            }
          })

          modelMap.forEach((data, modelName) => {
            const marker = `<span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${data.color};"></span>`
            result += `<div style="margin-top: 4px;">
              <div style="font-weight: 600; margin-bottom: 2px;">${marker}${modelName}</div>
              <div style="display: flex; justify-content: space-between; gap: 16px; padding-left: 14px;">
                <span style="color: #6b6b6b;">完成时间</span>
                <span style="font-weight: 600;">${data.total || 0}s</span>
              </div>
              <div style="display: flex; justify-content: space-between; gap: 16px; padding-left: 14px;">
                <span style="color: #6b6b6b;">首响时间</span>
                <span style="font-weight: 600;">${data.ttfb || 0}s</span>
              </div>
            </div>`
          })
          return result
        },
      },
      legend: {
        ...theme.legend,
        ...createModelLegendConfig(legendData),
        top: 0,
        right: 0,
        type: 'scroll',
        pageIconSize: 10,
        pageTextStyle: {
          fontSize: 10,
        },
        selectedMode: 'multiple',
      },
      grid: {
        ...theme.grid,
        top: modelNames.length > 3 ? 56 : 48,
        bottom: 32,
      },
      xAxis: {
        ...theme.xAxis,
        data: chartData.value.responseTime.labels,
      },
      yAxis: {
        ...theme.yAxis,
        axisLabel: {
          ...theme.yAxis.axisLabel,
          formatter: '{value}s',
        },
      },
      series: series,
    }, mode)

    // 监听图例选择事件，同步控制首响时间线的显示/隐藏
    const responseChart = charts.responseTime
    if (!responseChart) return
    responseChart.off?.('legendselectchanged')
    responseChart.on?.('legendselectchanged', (params: any) => {
      const selected = params.selected

      // 遍历所有模型，控制对应的ttfb线
      Object.keys(selected).forEach((modelName) => {
        const ttfbSeriesName = `${modelName}-ttfb`
        const isSelected = selected[modelName]

        // 使用dispatchAction来控制series的显示/隐藏
        responseChart.dispatchAction?.({
          type: isSelected ? 'legendSelect' : 'legendUnSelect',
          name: ttfbSeriesName,
        })
      })
    })

  }

  return {
    stats,
    timeRanges,
    timeRangeHourlyRequests,
    timeRangeTrend,
    timeRangeSuccessRate,
    timeRangeModel,
    timeRangeModelRank,
    timeRangeResponseTime,
    hourlyRequestsChartRef,
    trendChartRef,
    successRateChartRef,
    responseTimeChartRef,
    modelChartRef,
    modelRankChartRef,
  }
}
