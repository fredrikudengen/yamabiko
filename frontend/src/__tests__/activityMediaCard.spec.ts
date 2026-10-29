import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'

import type { ActivityMediaDto } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import ActivityMediaCard from '@/features/activities/components/ActivityMediaCard.vue'
import { useAuthStore } from '@/features/auth/stores/auth'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const ACTIVITY_ID = 5

const photo = (id: number): ActivityMediaDto => ({
  id,
  activity_id: ACTIVITY_ID,
  media_path: `/app/backend/data/activity_media/${ACTIVITY_ID}_${id}.jpg`,
  media_type: 1,
})

/** Stands in for the confirm dialog (a reka-ui portal): one button that confirms. */
const ConfirmDialogStub = {
  props: ['open'],
  emits: ['confirm', 'update:open'],
  template: '<button data-testid="confirm-delete" @click="$emit(\'confirm\')" />',
}

const mounted: VueWrapper[] = []

/**
 * Mounts the card with `photos` as what the media endpoint returns. `uploadResults` is the outcome of
 * each upload in turn (`true` succeeds, `false` fails); every upload succeeds when it is omitted.
 */
async function mountCard(
  props: { isOwner?: boolean },
  photos: ActivityMediaDto[] = [],
  uploadResults: boolean[] = [],
) {
  const uploads = [...uploadResults]
  vi.mocked(apiFetch).mockImplementation(async (_url: string, options?: { method?: string }) => {
    if (options?.method === 'POST') {
      if (uploads.shift() === false) {
        throw new Error('upload failed')
      }
      return photo(99)
    }
    if (options?.method === 'DELETE') {
      return undefined
    }
    return photos
  })
  const wrapper = mount(ActivityMediaCard, {
    props: { activityId: ACTIVITY_ID, ...props },
    attachTo: document.body,
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: { ConfirmDialog: ConfirmDialogStub },
    },
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

/** Puts `files` in the hidden file input as if they were chosen, and fires the change. */
async function chooseFiles(wrapper: VueWrapper, files: File[]) {
  const input = wrapper.find('[data-testid="media-file-input"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const image = (name: string) => new File(['x'], name, { type: 'image/jpeg' })

const toastMessages = () => useToasts().toasts.value.map((toast) => toast.message)

describe('ActivityMediaCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().isAuthenticated = true
    vi.mocked(apiFetch).mockReset()
  })

  afterEach(() => {
    while (mounted.length > 0) {
      mounted.pop()!.unmount()
    }
  })

  it('shows the owner an add button and a hint when there are no photos yet', async () => {
    const wrapper = await mountCard({ isOwner: true })

    expect(wrapper.text()).toContain('Photos')
    expect(wrapper.text()).toContain('Add photo')
    expect(wrapper.text()).toContain('No photos yet')
    expect(wrapper.find('li').exists()).toBe(false)
  })

  it('shows nothing to someone else when there are no photos', async () => {
    const wrapper = await mountCard({ isOwner: false })

    expect(wrapper.find('h2').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })

  it('shows the photos to someone else, without add or delete buttons', async () => {
    const wrapper = await mountCard({ isOwner: false }, [photo(1), photo(2)])

    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.find('[data-testid="media-file-input"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Add photo')
    expect(wrapper.find('button[aria-label="Delete photo"]').exists()).toBe(false)
  })

  it('opens the file picker from the add button', async () => {
    const wrapper = await mountCard({ isOwner: true })
    const input = wrapper.find<HTMLInputElement>('[data-testid="media-file-input"]').element
    const click = vi.spyOn(input, 'click')

    const add = wrapper.findAll('button').find((b) => b.text() === 'Add photo')!
    await add.trigger('click')

    expect(click).toHaveBeenCalledTimes(1)
  })

  describe('uploading', () => {
    it('uploads every chosen image and reports once for the batch', async () => {
      const wrapper = await mountCard({ isOwner: true })
      await chooseFiles(wrapper, [image('a.jpg'), image('b.jpg')])

      const posts = vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'POST')
      expect(posts).toHaveLength(2)
      expect(posts[0]![0]).toBe(`/activities_media/upload/activity_id/${ACTIVITY_ID}`)
      expect(((posts[0]![1] as { body: FormData }).body.get('file') as File).name).toBe('a.jpg')
      expect(toastMessages()).toContain('2 photos uploaded')
    })

    it('says "Photo uploaded" for a single photo', async () => {
      const wrapper = await mountCard({ isOwner: true })
      await chooseFiles(wrapper, [image('a.jpg')])

      expect(toastMessages()).toContain('Photo uploaded')
    })

    it('skips files that are not images and says so', async () => {
      const wrapper = await mountCard({ isOwner: true })
      await chooseFiles(wrapper, [
        image('a.jpg'),
        new File(['x'], 'notes.pdf', { type: 'application/pdf' }),
      ])

      const posts = vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'POST')
      expect(posts).toHaveLength(1)
      expect(toastMessages()).toContain('Please choose an image file.')
      expect(toastMessages()).toContain('Photo uploaded')
    })

    it('uploads nothing when only non-images are chosen', async () => {
      const wrapper = await mountCard({ isOwner: true })
      await chooseFiles(wrapper, [new File(['x'], 'notes.pdf', { type: 'application/pdf' })])

      expect(vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'POST')).toHaveLength(0)
      expect(toastMessages()).toContain('Please choose an image file.')
    })

    it('reports how many went through when some fail, and keeps going after a failure', async () => {
      const wrapper = await mountCard({ isOwner: true }, [], [false, true, true])
      await chooseFiles(wrapper, [image('a.jpg'), image('b.jpg'), image('c.jpg')])

      const posts = vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'POST')
      expect(posts).toHaveLength(3)
      expect(toastMessages()).toContain('2 of 3 photos uploaded')
    })

    it('reports an error when every upload fails', async () => {
      const wrapper = await mountCard({ isOwner: true }, [], [false])
      await chooseFiles(wrapper, [image('a.jpg')])

      expect(toastMessages()).toContain("Couldn't upload the photo")
    })

    it('locks the add button while uploading and frees it afterwards', async () => {
      let finish: () => void = () => {}
      const wrapper = await mountCard({ isOwner: true })
      vi.mocked(apiFetch).mockImplementation(
        async (_url: string, options?: { method?: string }) => {
          if (options?.method === 'POST') {
            await new Promise<void>((resolve) => {
              finish = resolve
            })
            return photo(99)
          }
          return []
        },
      )
      const addButton = () => wrapper.findAll('button').find((b) => b.text() === 'Add photo')!

      const pending = chooseFiles(wrapper, [image('a.jpg')])
      await flushPromises()
      expect(addButton().attributes('disabled')).toBeDefined()

      finish()
      await pending
      expect(addButton().attributes('disabled')).toBeUndefined()
    })

    it('does nothing when the picker is closed without a choice', async () => {
      const wrapper = await mountCard({ isOwner: true })
      await chooseFiles(wrapper, [])

      expect(vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'POST')).toHaveLength(0)
    })
  })

  it('deletes a photo after the owner confirms', async () => {
    const wrapper = await mountCard({ isOwner: true }, [photo(1), photo(2)])

    await wrapper.findAll('button[aria-label="Delete photo"]')[1]!.trigger('click')
    expect(vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'DELETE')).toHaveLength(0)

    await wrapper.find('[data-testid="confirm-delete"]').trigger('click')
    await flushPromises()

    const deletes = vi.mocked(apiFetch).mock.calls.filter(([, o]) => o?.method === 'DELETE')
    expect(deletes).toHaveLength(1)
    expect(deletes[0]![0]).toBe('/activities_media/2')
    expect(toastMessages()).toContain('Photo deleted')
  })

  describe('viewer', () => {
    const dialog = () => document.body.querySelector('[role="dialog"]')

    it('opens at the clicked photo, steps with the arrow keys and closes with Escape', async () => {
      const wrapper = await mountCard({ isOwner: false }, [photo(1), photo(2), photo(3)])
      expect(dialog()).toBeNull()

      await wrapper.findAll('button[aria-label="View full size"]')[1]!.trigger('click')
      expect(dialog()).not.toBeNull()
      expect(dialog()!.textContent).toContain('2 / 3')

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
      await flushPromises()
      expect(dialog()!.textContent).toContain('3 / 3')

      // The last photo has no next one.
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
      await flushPromises()
      expect(dialog()!.textContent).toContain('3 / 3')

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
      await flushPromises()
      expect(dialog()!.textContent).toContain('2 / 3')

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      await flushPromises()
      expect(dialog()).toBeNull()
    })

    it('listens for keys only while it is open, and stops when it closes or goes away', async () => {
      const add = vi.spyOn(document, 'addEventListener')
      const remove = vi.spyOn(document, 'removeEventListener')
      const keydown = (spy: typeof add) => spy.mock.calls.filter(([type]) => type === 'keydown')
      try {
        const wrapper = await mountCard({ isOwner: false }, [photo(1), photo(2)])
        expect(keydown(add)).toHaveLength(0)

        await wrapper.findAll('button[aria-label="View full size"]')[0]!.trigger('click')
        expect(keydown(add)).toHaveLength(1)

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
        await flushPromises()
        expect(keydown(remove).length).toBeGreaterThanOrEqual(1)
        // The listener that was added is the one that was removed.
        expect(keydown(remove).map(([, fn]) => fn)).toContain(keydown(add)[0]![1])
      } finally {
        add.mockRestore()
        remove.mockRestore()
      }
    })
  })
})
