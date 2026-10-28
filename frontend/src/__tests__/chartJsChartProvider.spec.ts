import { describe, expect, it } from 'vitest'

import { setChartProvider, useChartProvider } from '@/composables/useChartProvider'
import type { ChartBand } from '@/composables/useChartProvider'

import {
  bandGradientStops,
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

describe('series coloured by value bands', () => {
  const BANDS: ChartBand[] = [
    { from: Number.NEGATIVE_INFINITY, color: '#111111' },
    { from: 100, color: '#222222' },
    { from: 120, color: '#333333' },
    { from: 140, color: '#444444' },
  ]
  // Plot area 100..300 px; values 80..180 map to pixels 300..100 (higher value higher up).
  const area = { top: 100, bottom: 300 }
  const upright = {
    min: 80,
    max: 180,
    getPixelForValue: (value: number) => 300 - (value - 80) * 2,
  }
  const inverted = {
    min: 80,
    max: 180,
    getPixelForValue: (value: number) => 100 + (value - 80) * 2,
  }

  it('puts a hard colour edge at every band limit, from the top edge down', () => {
    // 2 px per unit over 200 px: 180..140 -> 0..0.4, 140..120 -> 0.4..0.6, 120..100 -> 0.6..0.8,
    // below 100 -> 0.8..1.
    const stops = bandGradientStops(BANDS, area, upright, null)

    expect(stops.map((s) => s.color)).toEqual([
      '#444444',
      '#444444',
      '#333333',
      '#333333',
      '#222222',
      '#222222',
      '#111111',
      '#111111',
    ])
    expect(stops.map((s) => s.offset)).toEqual([0, 0.4, 0.4, 0.6, 0.6, 0.8, 0.8, 1])
  })

  it('follows an inverted axis, where the lowest band is at the top', () => {
    const stops = bandGradientStops(BANDS, area, inverted, null)

    expect(stops.map((s) => s.color)).toEqual([
      '#111111',
      '#111111',
      '#222222',
      '#222222',
      '#333333',
      '#333333',
      '#444444',
      '#444444',
    ])
    expect(stops.map((s) => s.offset)).toEqual([0, 0.2, 0.2, 0.4, 0.4, 0.6, 0.6, 1])
  })

  it('leaves out bands outside the visible range and cuts the ones that stick out', () => {
    // Only 110..130 is visible: the lowest and the highest band are out of view.
    const narrow = {
      min: 110,
      max: 130,
      getPixelForValue: (value: number) => 300 - (value - 110) * 10,
    }
    const stops = bandGradientStops(BANDS, area, narrow, null)

    expect(stops.map((s) => s.color)).toEqual(['#333333', '#333333', '#222222', '#222222'])
    expect(stops.map((s) => s.offset)).toEqual([0, 0.5, 0.5, 1])
  })

  it('applies an opacity to the colours, and returns nothing for an empty plot area', () => {
    const stops = bandGradientStops([{ from: 0, color: '#ff0000' }], area, upright, 0.15)

    expect(stops.map((s) => s.color)).toEqual(['rgba(255, 0, 0, 0.15)', 'rgba(255, 0, 0, 0.15)'])
    expect(bandGradientStops(BANDS, { top: 50, bottom: 50 }, upright, null)).toEqual([])
  })

  /** A chart stub that records the gradient the provider builds. */
  function fakeChart(chartArea: { top: number; bottom: number } | undefined) {
    const added: { offset: number; color: string }[] = []
    const gradientArgs: number[][] = []
    const gradient = {
      addColorStop: (offset: number, color: string) => added.push({ offset, color }),
    }
    const chart = {
      chartArea,
      scales: { y: upright },
      ctx: {
        createLinearGradient: (...args: number[]) => {
          gradientArgs.push(args)
          return gradient
        },
      },
    }
    return { chart, added, gradientArgs }
  }
  const banded = () =>
    buildChartConfiguration({
      kind: 'line',
      labels: ['a'],
      series: [{ label: 'HR', data: [120], color: '#e24b4a', bands: BANDS }],
    }).data.datasets[0] as unknown as Record<string, unknown>

  it('paints the line opaque and the area translucent from the bands', () => {
    const dataset = banded()
    const line = fakeChart(area)
    const fill = fakeChart(area)

    const border = (dataset.borderColor as (ctx: unknown) => unknown)({ chart: line.chart })
    const background = (dataset.backgroundColor as (ctx: unknown) => unknown)({ chart: fill.chart })

    expect(border).toBeDefined()
    expect(background).toBeDefined()
    // A vertical gradient over the plot area.
    expect(line.gradientArgs).toEqual([[0, 100, 0, 300]])
    expect(line.added[0]).toEqual({ offset: 0, color: '#444444' })
    expect(line.added).toHaveLength(8)
    expect(fill.added[0]).toEqual({ offset: 0, color: 'rgba(68, 68, 68, 0.15)' })
  })

  it('falls back to the series colour before the chart has a plot area', () => {
    const dataset = banded()
    const { chart } = fakeChart(undefined)

    expect((dataset.borderColor as (ctx: unknown) => unknown)({ chart })).toBe('#e24b4a')
    expect((dataset.backgroundColor as (ctx: unknown) => unknown)({ chart })).toBe(
      'rgba(226, 75, 74, 0.15)',
    )
  })

  it('keeps series without bands, and bar charts, as plain colours', () => {
    const plain = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1], color: '#e24b4a' }],
    }).data.datasets[0] as unknown as Record<string, unknown>
    const bar = buildChartConfiguration({
      kind: 'bar',
      series: [{ label: 'HR', data: [1], color: '#e24b4a', bands: BANDS }],
    }).data.datasets[0] as unknown as Record<string, unknown>

    expect(plain.borderColor).toBe('#e24b4a')
    expect(plain.backgroundColor).toBe('rgba(226, 75, 74, 0.15)')
    expect(bar.borderColor).toBe('#e24b4a')
    expect(bar.backgroundColor).toBe('#e24b4a')
  })
})
