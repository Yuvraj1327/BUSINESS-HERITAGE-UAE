import { apiClient } from '@/lib/api-client'
import { supabase } from '@/lib/supabase'
import { AVATAR_MAX_BYTES, AVATAR_TYPES } from '@/schemas/settings'
import type { Preferences } from '@/schemas/preferences'
import { profileSchema, type UserProfile } from '@/schemas/auth'

function client() {
  if (!supabase) throw new Error('Supabase is not configured')
  return supabase
}

const BUCKET = 'avatars'

/** Own name / phone / photo only. The server refuses anything else (no role, branch or status). */
export async function updateOwnProfile(patch: {
  full_name?: string
  phone?: string | null
  avatar_path?: string | null
}): Promise<UserProfile> {
  const { data } = await apiClient.patch<unknown>('/auth/profile', patch)
  return profileSchema.parse(data)
}

export async function saveOwnPreferences(preferences: Preferences): Promise<UserProfile> {
  const { data } = await apiClient.put<unknown>('/auth/preferences', preferences)
  return profileSchema.parse(data)
}

/* ---------- profile photo (Supabase Storage, private bucket, own folder only) ---------- */

export class AvatarError extends Error {}

const SIGNATURES: Record<string, number[][]> = {
  'image/jpeg': [[0xff, 0xd8, 0xff]],
  'image/png': [[0x89, 0x50, 0x4e, 0x47]],
  'image/webp': [[0x52, 0x49, 0x46, 0x46]], // "RIFF"; "WEBP" follows at byte 8
}

function readHead(file: File): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.onerror = () => reject(new AvatarError('The file could not be read.'))
    reader.readAsArrayBuffer(file.slice(0, 12))
  })
}

/** Type, size and real file signature (a renamed file is not enough). Storage enforces the same on the server. */
export async function validateAvatar(file: File): Promise<keyof typeof AVATAR_TYPES> {
  if (!(file.type in AVATAR_TYPES)) throw new AvatarError('Use a JPG, PNG or WebP image.')
  if (file.size === 0) throw new AvatarError('The file is empty.')
  if (file.size > AVATAR_MAX_BYTES) throw new AvatarError('The image must be 2 MB or smaller.')
  const head = await readHead(file)
  const ok = SIGNATURES[file.type]?.some((sig) => sig.every((b, i) => head[i] === b))
  const webpOk = file.type !== 'image/webp' || String.fromCharCode(...head.slice(8, 12)) === 'WEBP'
  if (!ok || !webpOk) throw new AvatarError('This file is not a valid image.')
  return file.type as keyof typeof AVATAR_TYPES
}

/** Uploads to `<user id>/avatar-<uuid>.<ext>` and returns the object path (Storage RLS enforces the folder). */
export async function uploadAvatar(userId: string, file: File): Promise<string> {
  const type = await validateAvatar(file)
  const path = `${userId}/avatar-${crypto.randomUUID()}.${AVATAR_TYPES[type]}`
  const { error } = await client().storage.from(BUCKET).upload(path, file, {
    contentType: type,
    cacheControl: '3600',
    upsert: false,
  })
  if (error) throw new AvatarError('The photo could not be uploaded. Please try again.')
  return path
}

export async function removeAvatarObject(path: string | null | undefined): Promise<void> {
  if (!path || !supabase) return
  await supabase.storage.from(BUCKET).remove([path]) // best effort: an orphan is harmless and private
}

export async function getAvatarUrl(path: string): Promise<string | null> {
  if (!supabase) return null
  const { data, error } = await supabase.storage.from(BUCKET).createSignedUrl(path, 3600)
  return error ? null : data.signedUrl
}

/* ---------- Supabase Auth: password, email, sessions ---------- */

/** Re-checks the current password first, so a left-open session cannot be used to take over the account. */
export async function changePassword(email: string, current: string, next: string) {
  const { error: reauth } = await client().auth.signInWithPassword({ email, password: current })
  if (reauth) throw new Error('Your current password is not correct.')
  const { error } = await client().auth.updateUser({ password: next })
  if (error) throw error
}

/** Supabase emails a confirmation link; the address only changes once it is confirmed. */
export async function requestEmailChange(currentEmail: string, current: string, newEmail: string) {
  const { error: reauth } = await client().auth.signInWithPassword({
    email: currentEmail,
    password: current,
  })
  if (reauth) throw new Error('Your current password is not correct.')
  const { error } = await client().auth.updateUser(
    { email: newEmail },
    { emailRedirectTo: `${window.location.origin}/settings/security` },
  )
  if (error) throw error
}

/** Ends every other session of this account; this device stays signed in. */
export async function signOutOtherDevices() {
  const { error } = await client().auth.signOut({ scope: 'others' })
  if (error) throw error
}
