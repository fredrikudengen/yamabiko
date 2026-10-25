import { describe, expect, it } from 'vitest'

import { setChartProvider, useChartProvider } from '@/composables/useChartProvider'
import {
  buildChartConfiguration,
  createChartJsChartProvider,
  DEFAULT_CHART_PALETTE,
} from '@/providers/chartJsChartProvider'

describe('buildChartConfiguration', () => {
  it('maps a line chart with smoothing and a flat translucent fill', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      labels: ['a', 'b'],
      series: [{ label: 'Pace', data: [1, 2] }],
    })

    expect(config.type).toBe('line')
    expect(config.data.labels).toEqual(['a', 'b'])

    const dataset = config.data.datasets[0] as Record<string, unknown> | undefined
    expect(dataset?.label).toBe('Pace')
    expect(dataset?.data).toEqual([1, 2])
    expect(dataset?.fill).toBe(true)
    // Flat translucent fill (not a gradient), per the design system.
    expect(dataset?.backgroundColor).toBe('rgba(29, 158, 117, 0.15)')
    expect(dataset?.tension).toBe(0.3)
  })

  it('fills the area for area charts while staying a line type', () => {
    const config = buildChartConfiguration({
      kind: 'area',
      series: [{ label: 'Elevation', data: [3] }],
    })

    expect(config.type).toBe('line')
    const dataset = config.data.datasets[0] as Record<string, unknown> | undefined
    expect(dataset?.fill).toBe(true)
  })

  it('maps bar charts to the bar type', () => {
    const config = buildChartConfiguration({
      kind: 'bar',
      series: [{ label: 'Count', data: [5] }],
    })

    expect(config.type).toBe('bar')
  })

  it('renders a dashed series as a dashed line overlay regardless of chart kind', () => {
    const config = buildChartConfiguration({
      kind: 'bar',
      series: [
        { label: 'Count', data: [1, 2] },
        { label: 'Target', data: [3, 3], dashed: true },
      ],
    })

    expect(config.type).toBe('bar')
    const datasets = config.data.datasets as unknown as Record<string, unknown>[]
    // The data series keeps the chart's bar geometry (no explicit per-dataset type).
    expect(datasets[0]?.type).toBeUndefined()
    // The dashed target is overlaid as a line with a dash pattern and no fill.
    expect(datasets[1]?.type).toBe('line')
    expect(datasets[1]?.borderDash).toEqual([6, 6])
    expect(datasets[1]?.fill).toBe(false)
    expect(datasets[1]?.pointRadius).toBe(0)
  })

  it('assigns palette colours by series index and honours explicit colours', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [
        { label: 'A', data: [1] },
        { label: 'B', data: [2], color: '#abcdef' },
      ],
    })

    const datasets = config.data.datasets as unknown as Record<string, unknown>[]
    expect(datasets[0]?.borderColor).toBe(DEFAULT_CHART_PALETTE[0])
    expect(datasets[1]?.borderColor).toBe('#abcdef')
  })

  it('defaults labels to an empty array when omitted', () => {
    const config = buildChartConfiguration({ kind: 'line', series: [] })
    expect(config.data.labels).toEqual([])
  })

  it('shows the legend only for multi-series charts', () => {
    const single = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'A', data: [1] }],
    })
    const multi = buildChartConfiguration({
      kind: 'line',
      series: [
        { label: 'A', data: [1] },
        { label: 'B', data: [2] },
      ],
    })

    expect(single.options?.plugins?.legend?.display).toBe(false)
    expect(multi.options?.plugins?.legend?.display).toBe(true)
  })

  it('applies the value formatter to y-axis ticks and inverts the axis when requested', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      valueFormat: (value) => `${value} bpm`,
      invertY: true,
    })

    const y = config.options?.scales?.y as Record<string, unknown> | undefined
    expect(y?.reverse).toBe(true)
    const ticks = y?.ticks as { callback?: (value: number) => string } | undefined
    expect(ticks?.callback?.(120)).toBe('120 bpm')
  })

  it('keeps the tint under the line on an inverted axis', () => {
    const fillOf = (invertY: boolean) => {
      const config = buildChartConfiguration({
        kind: 'line',
        series: [{ label: 'Pace', data: [1] }],
        invertY,
      })
      return (config.data.datasets[0] as Record<string, unknown> | undefined)?.fill
    }

    // Chart.js fills towards the axis minimum by default, which is the top edge once the axis is
    // inverted; 'start' is the bottom edge whichever way the axis points.
    expect(fillOf(true)).toBe('start')
    expect(fillOf(false)).toBe(true)
  })

  it('appends the x-axis unit to the tooltip title', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      labels: ['0.7'],
      xUnit: 'km',
    })
    const tooltip = config.options?.plugins?.tooltip as
      { callbacks?: { title?: (items: { label: string }[]) => string } } | undefined
    expect(tooltip?.callbacks?.title?.([{ label: '0.7' }])).toBe('0.7 km')
  })

  it('leaves the y-axis upright without explicit options', () => {
    const config = buildChartConfiguration({ kind: 'line', series: [{ label: 'A', data: [1] }] })
    const y = config.options?.scales?.y as Record<string, unknown> | undefined
    expect(y?.reverse).toBe(false)
  })

  it('adds pan/zoom config when zoom is enabled and omits it otherwise', () => {
    const zoomed = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      zoom: true,
    })
    const zoom = zoomed.options?.plugins?.zoom as { pan?: { enabled?: boolean } } | undefined
    expect(zoom?.pan?.enabled).toBe(true)

    const plain = buildChartConfiguration({ kind: 'line', series: [{ label: 'A', data: [1] }] })
    expect(plain.options?.plugins?.zoom).toBeUndefined()
  })
})

describe('createChartJsChartProvider', () => {
  it('names the provider and registers as available behind the seam', () => {
    const provider = createChartJsChartProvider()
    expect(provider.name).toBe('chartjs')

    setChartProvider(provider)
    const { provider: active, isAvailable } = useChartProvider()
    expect(active.name).toBe('chartjs')
    expect(isAvailable).toBe(true)
  })
})

describe('backdrop series and axis bounds', () => {
  const options = {
    kind: 'line' as const,
    labels: ['0.1', '0.2', '0.3'],
    series: [
      { label: 'Pace', data: [600, 620, 640] },
      {
        label: 'Elevation',
        data: [100, 200, 300],
        backdrop: true,
        color: '#94a3b8',
        format: (v: number) => `${Math.round(v)} m`,
      },
    ],
    valueFormat: (v: number) => `pace ${v}`,
    yMin: 540,
    yMax: 720,
  }

  it('draws the backdrop behind the other series on its own hidden axis', () => {
    const config = buildChartConfiguration(options)
    const [pace, backdrop] = config.data.datasets as unknown as Record<string, unknown>[]

    expect(pace?.yAxisID).toBeUndefined()
    expect(backdrop).toMatchObject({
      yAxisID: 'backdrop',
      fill: 'start',
      order: 10,
      backgroundColor: 'rgba(148, 163, 184, 0.25)',
    })
    const scales = config.options?.scales as Record<string, Record<string, unknown>>
    expect(scales.backdrop).toMatchObject({ display: false })
  })

  it('scales the backdrop axis so the series fills the lower part of the chart', () => {
    const scales = buildChartConfiguration(options).options?.scales as Record<
      string,
      { min?: number; max?: number }
    >

    // Range 100..300: a little room below, 60 % headroom above.
    expect(scales.backdrop?.min).toBe(90)
    expect(scales.backdrop?.max).toBe(420)
  })

  it('survives a backdrop series with no finite values', () => {
    const config = buildChartConfiguration({
      ...options,
      series: [options.series[0]!, { ...options.series[1]!, data: [Number.NaN, Number.NaN] }],
    })
    const scales = config.options?.scales as Record<string, { min?: number; max?: number }>

    expect(scales.backdrop?.min).toBeUndefined()
    expect(scales.backdrop?.max).toBeUndefined()
  })

  it('applies the y bounds to the main axis only', () => {
    const scales = buildChartConfiguration(options).options?.scales as Record<
      string,
      { min?: number; max?: number }
    >

    expect(scales.y).toMatchObject({ min: 540, max: 720 })
  })

  it('formats each series with its own formatter in the tooltip', () => {
    const config = buildChartConfiguration(options)
    type TooltipLabel = (ctx: {
      parsed: { y: number }
      datasetIndex: number
      dataset: { label: string }
    }) => string
    const tooltip = config.options?.plugins?.tooltip as { callbacks: { label: TooltipLabel } }
    const label = tooltip.callbacks.label

    expect(label({ parsed: { y: 610 }, datasetIndex: 0, dataset: { label: 'Pace' } })).toBe(
      'Pace: pace 610',
    )
    expect(label({ parsed: { y: 123.4 }, datasetIndex: 1, dataset: { label: 'Elevation' } })).toBe(
      'Elevation: 123 m',
    )
  })

  it('shows every series at the hovered position only when there is a backdrop', () => {
    expect(buildChartConfiguration(options).options?.interaction).toEqual({
      mode: 'index',
      intersect: false,
    })
    expect(
      buildChartConfiguration({ ...options, series: [options.series[0]!] }).options?.interaction,
    ).toBeUndefined()
  })

  it('leaves charts without a backdrop or bounds as they were', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      labels: ['a'],
      series: [{ label: 'Pace', data: [1] }],
    })
    const scales = config.options?.scales as Record<string, { min?: number; max?: number }>

    expect(Object.keys(scales)).toEqual(['x', 'y'])
    expect(scales.y?.min).toBeUndefined()
    expect(scales.y?.max).toBeUndefined()
  })
})
