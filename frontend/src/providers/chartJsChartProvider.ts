/**
 * Concrete Chart.js implementation of the {@link ChartProvider} seam. Registered
 * during bootstrap so Activity and Home surfaces can render metric charts. Kept
 * behind the seam so minimal builds can omit Chart.js entirely.
 *
 * The pure {@link buildChartConfiguration} helper is exported so the seam →
 * Chart.js translation can be unit-tested without a canvas.
 */
import {
  Chart,
  registerables,
  type ChartConfiguration,
  type ChartDataset,
  type ScriptableContext,
} from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'

import type {
  ChartBand,
  ChartInstance,
  ChartProvider,
  ChartRenderOptions,
} from '@/composables/useChartProvider'

Chart.register(...registerables, zoomPlugin)

/** Design-token-aligned series palette, brand teal first. */
export const DEFAULT_CHART_PALETTE: readonly string[] = [
  '#1d9e75',
  '#2563eb',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#14b8a6',
]

/** Configuration for the Chart.js provider. */
export interface ChartJsChartProviderConfig {
  /** Colour palette used for series without an explicit colour. */
  palette?: readonly string[]
}

/**
 * Picks a deterministic colour for a series, honouring an explicit colour when
 * provided and otherwise cycling the palette.
 *
 * @param index - Zero-based series index.
 * @param explicit - The series' own colour, if any.
 * @param palette - Palette to cycle when no explicit colour is set.
 * @returns A concrete colour string.
 */
function colorFor(index: number, explicit: string | undefined, palette: readonly string[]): string {
  if (explicit) {
    return explicit
  }
  // The literal fallback guards the (impossible in practice) empty-palette case
  // so the return type stays a non-nullable string under noUncheckedIndexedAccess.
  return palette[index % palette.length] ?? DEFAULT_CHART_PALETTE[0] ?? '#1d9e75'
}

/** Converts a 6-digit hex colour to an `rgba()` string at the given alpha. */
function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '')
  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * Opacity of the flat fill under line/area charts. A calm translucent tint
 * rather than a gradient, per the design system's "flat fills with opacity"
 * rule.
 */
const AREA_FILL_ALPHA = 0.15

/** Id of the hidden y-axis a backdrop series is drawn against. */
const BACKDROP_AXIS = 'backdrop'
/** Chart.js draws higher `order` first, so the backdrop sits behind the other series. */
const BACKDROP_ORDER = 10
const BACKDROP_FILL_ALPHA = 0.25
const BACKDROP_LINE_ALPHA = 0.5
/** The backdrop fills the lower part of the chart: this much headroom above its highest point (as a share of its range). */
const BACKDROP_HEADROOM = 0.6
/** And this much room below its lowest point. */
const BACKDROP_FLOOR = 0.05

/**
 * The bounds of the hidden axis for a backdrop series, chosen so the series fills the lower part of
 * the chart instead of the whole height.
 *
 * @param series - The backdrop series.
 * @returns Axis bounds, or `undefined` when the series has no finite values.
 */
function backdropBounds(
  series: ChartRenderOptions['series'][number],
): { min: number; max: number } | undefined {
  const values = series.data.filter(Number.isFinite)
  if (values.length === 0) {
    return undefined
  }
  const low = Math.min(...values)
  const high = Math.max(...values)
  const range = high - low || 1
  return { min: low - range * BACKDROP_FLOOR, max: high + range * BACKDROP_HEADROOM }
}

/** A colour stop of a banded gradient: `offset` is 0 at the top edge of the plot area, 1 at the bottom. */
export interface BandStop {
  offset: number
  color: string
}

/**
 * The colour stops of a vertical gradient that paints each value band in its own colour, with a hard
 * edge at every band limit. The stops follow the y-scale, so they hold on an inverted axis, and a band
 * outside the visible range gets no stops.
 *
 * @param bands - The bands, ascending by `from`.
 * @param area - The top and bottom edge of the plot area, in pixels.
 * @param scale - The y-scale: the pixel of a value.
 * @param alpha - Opacity for the colours (the fill), or `null` to keep them opaque (the line).
 * @returns Stops in increasing offset order, ready to add to a canvas gradient in that order.
 */
export function bandGradientStops(
  bands: readonly ChartBand[],
  area: { top: number; bottom: number },
  scale: { getPixelForValue(value: number): number },
  alpha: number | null,
): BandStop[] {
  const height = area.bottom - area.top
  if (!(height > 0)) {
    return []
  }
  // A limit outside the visible range lands beyond the plot area (Chart.js clamps an infinite value
  // to a far-off pixel), so keeping the offset within 0..1 cuts the band at the edge.
  const offsetOf = (value: number): number => {
    const offset = (scale.getPixelForValue(value) - area.top) / height
    return Math.min(Math.max(offset, 0), 1)
  }
  const ranges = bands.flatMap((band, index) => {
    const next = bands[index + 1]
    const a = offsetOf(band.from)
    const b = offsetOf(next ? next.from : Number.POSITIVE_INFINITY)
    const top = Math.min(a, b)
    const bottom = Math.max(a, b)
    return bottom > top ? [{ top, bottom, color: band.color }] : []
  })
  // The bands tile the axis, so once ordered from the top edge each one starts where the one above
  // it ends: the pair of stops at that offset is what makes the edge hard.
  ranges.sort((x, y) => x.top - y.top)
  return ranges.flatMap(({ top, bottom, color }) => {
    const paint = alpha === null ? color : hexToRgba(color, alpha)
    return [
      { offset: top, color: paint },
      { offset: bottom, color: paint },
    ]
  })
}

/**
 * A scriptable colour for a series coloured by value bands: a vertical gradient fitted to the plot
 * area and y-scale at the time the chart is drawn. Falls back to the series colour before the first
 * layout, when there is no plot area yet.
 */
function bandPaint(
  bands: readonly ChartBand[],
  fallback: string,
  alpha: number | null,
): (context: ScriptableContext<'line'>) => string | CanvasGradient {
  return ({ chart }) => {
    const area = chart.chartArea
    const scale = chart.scales.y
    if (!area || !scale) {
      return fallback
    }
    const stops = bandGradientStops(bands, area, scale, alpha)
    if (stops.length === 0) {
      return fallback
    }
    const gradient = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom)
    for (const stop of stops) {
      gradient.addColorStop(stop.offset, stop.color)
    }
    return gradient
  }
}

/**
 * Translates seam {@link ChartRenderOptions} into a Chart.js configuration.
 * Pure and deterministic so it can be unit-tested without a canvas.
 *
 * @param options - The chart to render.
 * @param palette - Optional colour palette for series without explicit colours.
 * @returns A Chart.js configuration object.
 */
export function buildChartConfiguration(
  options: ChartRenderOptions,
  palette: readonly string[] = DEFAULT_CHART_PALETTE,
): ChartConfiguration<'line' | 'bar'> {
  const type: 'line' | 'bar' = options.kind === 'bar' ? 'bar' : 'line'
  const backdrop = options.series.find((series) => series.backdrop)

  const datasets: ChartDataset<'line' | 'bar'>[] = options.series.map((series, index) => {
    const color = colorFor(index, series.color, palette)
    // A backdrop series is a muted area behind the rest (a height profile behind a pace line). It sits
    // on its own hidden axis, so it needs no unit in common with the main series.
    if (series.backdrop) {
      return {
        type: 'line',
        label: series.label,
        data: series.data,
        yAxisID: BACKDROP_AXIS,
        borderColor: hexToRgba(color, BACKDROP_LINE_ALPHA),
        backgroundColor: hexToRgba(color, BACKDROP_FILL_ALPHA),
        borderWidth: 1,
        fill: 'start',
        tension: 0.2,
        pointRadius: 0,
        order: BACKDROP_ORDER,
      }
    }
    // A dashed series is a reference/target line: render it as a dashed line
    // overlay regardless of the chart's geometry, so it sits on top of bars as a
    // mixed bar/line chart — mirroring v1's dashed target lines.
    if (series.dashed) {
      return {
        type: 'line',
        label: series.label,
        data: series.data,
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        borderDash: [6, 6],
        fill: false,
        tension: 0,
        pointRadius: 0,
      }
    }
    // Line/area charts get a flat translucent fill below the line (a calm tint,
    // not a gradient — per the design system); bars stay solid.
    const filled = type === 'line'
    // A series coloured by value (heart rate in its zones) paints line and fill with the bands.
    const banded = filled && series.bands && series.bands.length > 0 ? series.bands : null
    return {
      label: series.label,
      data: series.data,
      borderColor: banded ? bandPaint(banded, color, null) : color,
      backgroundColor: banded
        ? bandPaint(banded, hexToRgba(color, AREA_FILL_ALPHA), AREA_FILL_ALPHA)
        : filled
          ? hexToRgba(color, AREA_FILL_ALPHA)
          : color,
      borderWidth: 2,
      // On an inverted axis the default fill runs to the top edge (where the axis minimum now is), so
      // fill to the bottom edge of the chart instead ('start' is the bottom edge, whichever way the
      // axis points) and keep the tint under the line.
      fill: filled && options.invertY ? 'start' : filled,
      tension: 0.3,
      pointRadius: 0,
    }
  })

  return {
    type,
    data: {
      labels: options.labels ?? [],
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: options.series.length > 1 },
        tooltip: {
          callbacks: {
            // X value (tooltip title): append the axis unit (e.g. `0.7 km`) so a
            // hover is self-describing. Distance-less charts pass no unit.
            title: (items) => {
              const raw = items[0]?.label ?? ''
              return options.xUnit && raw ? `${raw} ${options.xUnit}` : raw
            },
            // Y value: `<series>: <formatted>` using the domain formatter.
            label: (ctx) => {
              const y = ctx.parsed.y
              if (y === null || y === undefined) {
                return ctx.dataset.label ?? ''
              }
              // A series may format its own values (a height next to a pace).
              const format = options.series[ctx.datasetIndex]?.format ?? options.valueFormat
              const formatted = format?.(y) ?? String(y)
              return ctx.dataset.label ? `${ctx.dataset.label}: ${formatted}` : formatted
            },
          },
        },
        // Interactive pan/zoom along the distance axis; wheel + drag on
        // desktop, pinch on touch (the v2 plugin handles pinch natively).
        zoom: options.zoom
          ? {
              zoom: {
                wheel: { enabled: true },
                pinch: { enabled: true },
                mode: 'x',
              },
              pan: { enabled: true, mode: 'x' },
            }
          : undefined,
      },
      // With a backdrop the tooltip shows every series at the hovered position (the pace and the height
      // there), not only the one nearest the pointer. Other charts keep Chart.js's default.
      interaction: backdrop ? { mode: 'index', intersect: false } : undefined,
      scales: {
        x: { display: true },
        y: {
          display: true,
          reverse: options.invertY ?? false,
          min: options.yMin,
          max: options.yMax,
          ticks: options.valueFormat
            ? { callback: (value) => options.valueFormat?.(Number(value)) ?? String(value) }
            : {},
        },
        ...(backdrop
          ? {
              [BACKDROP_AXIS]: {
                display: false,
                position: 'right' as const,
                ...backdropBounds(backdrop),
              },
            }
          : {}),
      },
    },
  }
}

/**
 * Creates a Chart.js-backed chart provider.
 *
 * @param config - Optional palette override.
 * @returns A {@link ChartProvider} ready to register via `setChartProvider`.
 */
export function createChartJsChartProvider(config: ChartJsChartProviderConfig = {}): ChartProvider {
  const palette = config.palette ?? DEFAULT_CHART_PALETTE

  return {
    name: 'chartjs',
    mount(target: HTMLElement, options: ChartRenderOptions): ChartInstance {
      const canvas = document.createElement('canvas')
      target.replaceChildren(canvas)

      const initialConfig = buildChartConfiguration(options, palette)
      let currentType = initialConfig.type
      let chart = new Chart(canvas, initialConfig)

      return {
        update(next: ChartRenderOptions): void {
          const nextConfig = buildChartConfiguration(next, palette)
          // Chart.js can't swap a chart's geometry in place, so recreate when
          // the kind changes; otherwise patch the data and re-render.
          if (currentType !== nextConfig.type) {
            chart.destroy()
            chart = new Chart(canvas, nextConfig)
            currentType = nextConfig.type
            return
          }
          chart.data = nextConfig.data
          chart.update()
        },
        destroy(): void {
          chart.destroy()
        },
      }
    },
  }
}
