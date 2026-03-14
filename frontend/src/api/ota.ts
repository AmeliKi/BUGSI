import { apiFetch } from './client'

export interface OtaPackage {
  id: string
  version: string
  description: string | null
  package_type: string
  file_size_bytes: number
  checksum_sha256: string
  commit_id: string | null
  created_by: string | null
  created_at: string
}

export interface OtaDeployment {
  id: string
  device_id: string
  ota_package_id: string
  status: string
  assigned_at: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string
}

export async function listPackages(offset = 0, limit = 50) {
  return apiFetch<OtaPackage[]>(`/ota/packages?offset=${offset}&limit=${limit}`)
}

export async function uploadPackage(file: File, version: string, packageType: string, description?: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('version', version)
  form.append('package_type', packageType)
  if (description) form.append('description', description)
  return apiFetch<OtaPackage>('/ota/packages', { method: 'POST', body: form })
}

export async function buildPackage(commitId: string, packageType: string, description?: string, version?: string) {
  return apiFetch<OtaPackage>('/ota/packages/build', {
    method: 'POST',
    body: JSON.stringify({
      commit_id: commitId,
      package_type: packageType,
      description: description || undefined,
      version: version || undefined,
    }),
  })
}

export async function deletePackage(id: string) {
  return apiFetch<void>(`/ota/packages/${id}`, { method: 'DELETE' })
}

export async function deployPackage(packageId: string, deviceIds: string[]) {
  return apiFetch<OtaDeployment[]>('/ota/deploy', {
    method: 'POST',
    body: JSON.stringify({ package_id: packageId, device_ids: deviceIds }),
  })
}

export async function listDeployments(params?: { device_id?: string; status?: string; package_id?: string }) {
  const qs = new URLSearchParams()
  if (params?.device_id) qs.set('device_id', params.device_id)
  if (params?.status) qs.set('status', params.status)
  if (params?.package_id) qs.set('package_id', params.package_id)
  return apiFetch<OtaDeployment[]>(`/ota/deployments?${qs}`)
}

export async function cancelDeployment(id: string) {
  return apiFetch<OtaDeployment>(`/ota/deployments/${id}/cancel`, { method: 'POST' })
}
