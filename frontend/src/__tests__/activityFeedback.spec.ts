import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ActivityFeedback } from '@/features/feedback/feedback'

import i18n from '@/i18n'
import ActivityFeedbackCard from '@/features/feedback/components/ActivityFeedbackCard.vue'
import { apiFetch } from '@/services/http'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const data = ref<ActivityFeedback | undefined>(undefined)
const mutate = vi.fn<(activityId: number) => void>()
const writing = ref(false)
const failed = ref(false)

vi.mock('@/features/feedback/feedback', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/feedback/feedback')>()),
  useActivityFeedbackQuery: () => ({ data }),
  useWriteActivityFeedbackMutation: () => ({ mutate, isPending: writing, isError: failed }),
}))

function mountCard() {
  return mount(ActivityFeedbackCard, { props: { activityId: 12 }, global: { plugins: [i18n] } })
}

function feedback(extra: Partial<ActivityFeedback> = {}): ActivityFeedback {
  return { enabled: true, pending: false, text: null, createdAt: null, ...extra }
}

describe('the feedback service', () => {
  it('reads and writes the feedback of one tour', async () => {
    const { fetchActivityFeedback, writeActivityFeedback } = await vi.importActual<
      typeof import('@/features/feedback/feedback')
    >('@/features/feedback/feedback')
    const dto = {
      enabled: true,
      pending: false,
      text: 'Fin tur.',
      model: 'claude-sonnet-5-5',
      created_at: '2026-11-11T10:00:00Z',
    }
    vi.mocked(apiFetch).mockResolvedValue(dto)

    const read = await fetchActivityFeedback(12)
    await writeActivityFeedback(12)

    expect(read).toEqual({
      enabled: true,
      pending: false,
      text: 'Fin tur.',
      createdAt: '2026-11-11T10:00:00Z',
    })
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/feedback/activities/12')
    expect(vi.mocked(apiFetch).mock.calls[1]).toEqual([
      '/feedback/activities/12',
      { method: 'POST' },
    ])
  })
})

describe('ActivityFeedbackCard', () => {
  beforeEach(() => {
    mutate.mockReset()
    writing.value = false
    failed.value = false
  })

  it('shows nothing when the feature is off, or before the answer is in', () => {
    data.value = undefined
    expect(mountCard().find('[data-testid="activity-feedback"]').exists()).toBe(false)

    data.value = feedback({ enabled: false })
    expect(mountCard().find('[data-testid="activity-feedback"]').exists()).toBe(false)
  })

  it('offers to write a text when there is none, and asks for it on click', async () => {
    data.value = feedback()
    const wrapper = mountCard()

    await wrapper.find('[data-testid="feedback-write"]').trigger('click')

    expect(mutate).toHaveBeenCalledWith(12)
    expect(wrapper.find('[data-testid="feedback-text"]').exists()).toBe(false)
  })

  it('shows the text with the day it was written, and can write it again', async () => {
    data.value = feedback({ text: 'Ny rekord på Løvstakken.', createdAt: '2026-11-11T10:00:00Z' })
    const wrapper = mountCard()

    expect(wrapper.find('[data-testid="feedback-text"]').text()).toBe('Ny rekord på Løvstakken.')
    expect(wrapper.text()).toContain('Written by Claude')
    expect(wrapper.text()).toContain('2026')
    await wrapper.find('[data-testid="feedback-rewrite"]').trigger('click')
    expect(mutate).toHaveBeenCalledWith(12)
  })

  it('says it is writing while a new tour waits for its text', () => {
    data.value = feedback({ pending: true })
    const wrapper = mountCard()

    expect(wrapper.text()).toContain('Writing')
    expect(wrapper.find('[data-testid="feedback-write"]').exists()).toBe(false)
  })

  it('says so when writing failed', () => {
    data.value = feedback()
    failed.value = true

    expect(mountCard().find('[role="alert"]').text()).toContain('Could not write')
  })
})
