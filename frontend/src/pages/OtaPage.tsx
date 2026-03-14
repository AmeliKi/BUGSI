import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Device } from '../api/devices'
import { listDevices } from '../api/devices'
import type { OtaDeployment, OtaPackage } from '../api/ota'
import {
  buildPackage,
  cancelDeployment,
  deployPackage,
  listDeployments,
  listPackages,
  uploadPackage,
} from '../api/ota'
import Pagination from '../components/Pagination'
import { cn, formatDate } from '../lib/utils'

const PAGE_SIZE = 20

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  downloading: 'bg-blue-100 text-blue-800',
  installing: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-gray-100 text-gray-600',
}

export default function OtaPage() {
  const { t } = useTranslation()
  const [packages, setPackages] = useState<OtaPackage[]>([])
  const [pkgTotal, setPkgTotal] = useState(0)
  const [pkgOffset, setPkgOffset] = useState(0)
  const [deployments, setDeployments] = useState<OtaDeployment[]>([])
  const [depTotal, setDepTotal] = useState(0)
  const [depOffset, setDepOffset] = useState(0)
  const [devices, setDevices] = useState<Device[]>([])
  const [showBuild, setShowBuild] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [showDeploy, setShowDeploy] = useState<string | null>(null)
  const [selectedDevices, setSelectedDevices] = useState<string[]>([])
  const [building, setBuilding] = useState(false)
  const [buildError, setBuildError] = useState<string | null>(null)

  const load = async () => {
    const [pkgs, deps, devs] = await Promise.all([
      listPackages(pkgOffset, PAGE_SIZE),
      listDeployments(),
      listDevices(),
    ])
    setPackages(pkgs.data)
    setPkgTotal(parseInt(pkgs.headers.get('X-Total-Count') || '0', 10))
    setDeployments(deps.data)
    setDepTotal(parseInt(deps.headers.get('X-Total-Count') || '0', 10))
    setDevices(devs.data)
  }

  useEffect(() => { load() }, [pkgOffset, depOffset])

  const handleBuild = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setBuildError(null)
    setBuilding(true)
    try {
      const form = new FormData(e.currentTarget)
      await buildPackage(
        form.get('commit_id') as string,
        form.get('package_type') as string,
        form.get('description') as string || undefined,
        form.get('version') as string || undefined,
      )
      setShowBuild(false)
      load()
    } catch (err: unknown) {
      setBuildError(err instanceof Error ? err.message : t('ota.build.error_fallback'))
    } finally {
      setBuilding(false)
    }
  }

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const file = form.get('file') as File
    await uploadPackage(
      file,
      form.get('version') as string,
      form.get('package_type') as string,
      form.get('description') as string || undefined,
    )
    setShowUpload(false)
    load()
  }

  const handleDeploy = async () => {
    if (!showDeploy || selectedDevices.length === 0) return
    await deployPackage(showDeploy, selectedDevices)
    setShowDeploy(null)
    setSelectedDevices([])
    load()
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('ota.title')}</h1>

      {/* Packages */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-800">{t('ota.packages')}</h2>
          <div className="flex gap-2">
            <button
              onClick={() => { setShowBuild(!showBuild); setShowUpload(false) }}
              className="bg-green-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-green-700"
            >
              {t('ota.build_from_git')}
            </button>
            <button
              onClick={() => { setShowUpload(!showUpload); setShowBuild(false) }}
              className="bg-gray-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-gray-700"
            >
              {t('ota.upload_package')}
            </button>
          </div>
        </div>

        {showBuild && (
          <form onSubmit={handleBuild} className="bg-white border rounded-md p-4 mb-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <input name="commit_id" required placeholder={t('ota.build.commit_placeholder')} className="px-3 py-2 border rounded-md text-sm" />
              <select name="package_type" required className="px-3 py-2 border rounded-md text-sm">
                <option value="full">{t('ota.type.full')}</option>
                <option value="daemon_only">{t('ota.type.daemon_only')}</option>
                <option value="config_only">{t('ota.type.config_only')}</option>
              </select>
              <input name="version" placeholder={t('ota.build.version_placeholder')} className="px-3 py-2 border rounded-md text-sm" />
            </div>
            <input name="description" placeholder={t('ota.build.description_placeholder')} className="w-full px-3 py-2 border rounded-md text-sm" />
            {buildError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">{buildError}</div>
            )}
            <button type="submit" disabled={building} className="bg-green-600 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50">
              {building ? t('ota.build.building') : t('ota.build.submit')}
            </button>
          </form>
        )}

        {showUpload && (
          <form onSubmit={handleUpload} className="bg-white border rounded-md p-4 mb-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <input name="version" required placeholder={t('ota.upload.version_placeholder')} className="px-3 py-2 border rounded-md text-sm" />
              <select name="package_type" required className="px-3 py-2 border rounded-md text-sm">
                <option value="full">{t('ota.type.full')}</option>
                <option value="daemon_only">{t('ota.type.daemon_only')}</option>
                <option value="config_only">{t('ota.type.config_only')}</option>
              </select>
              <input name="file" type="file" required className="text-sm" />
            </div>
            <input name="description" placeholder={t('ota.upload.description_placeholder')} className="w-full px-3 py-2 border rounded-md text-sm" />
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded-md text-sm">{t('ota.upload.submit')}</button>
          </form>
        )}

        <div className="bg-white rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.version')}</th>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.commit')}</th>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.type')}</th>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.size')}</th>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.created')}</th>
                <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {packages.map((pkg) => (
                <tr key={pkg.id}>
                  <td className="px-4 py-2 font-medium">{pkg.version}</td>
                  <td className="px-4 py-2 text-gray-600 font-mono text-xs">
                    {pkg.commit_id ? pkg.commit_id.slice(0, 7) : '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-600">{pkg.package_type}</td>
                  <td className="px-4 py-2 text-gray-600">{(pkg.file_size_bytes / 1024).toFixed(1)} KB</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(pkg.created_at)}</td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => { setShowDeploy(pkg.id); setSelectedDevices([]) }}
                      className="text-green-600 hover:underline text-xs mr-2"
                    >
                      {t('ota.deploy')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination offset={pkgOffset} limit={PAGE_SIZE} total={pkgTotal} onPageChange={setPkgOffset} />
      </div>

      {/* Deploy dialog */}
      {showDeploy && (
        <div className="bg-white border rounded-md p-4 mb-6">
          <h3 className="font-medium mb-2">{t('ota.deploy.title')}</h3>
          <div className="space-y-1 mb-3 max-h-40 overflow-y-auto">
            {devices.map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selectedDevices.includes(d.id)}
                  onChange={(e) => {
                    if (e.target.checked) setSelectedDevices([...selectedDevices, d.id])
                    else setSelectedDevices(selectedDevices.filter((id) => id !== d.id))
                  }}
                />
                {d.name} ({d.serial_number})
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleDeploy} disabled={selectedDevices.length === 0} className="bg-green-600 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50">
              {t('ota.deploy.submit', { count: selectedDevices.length })}
            </button>
            <button onClick={() => setShowDeploy(null)} className="px-4 py-2 border rounded-md text-sm">{t('ota.deploy.cancel')}</button>
          </div>
        </div>
      )}

      {/* Deployments */}
      <h2 className="text-lg font-semibold text-gray-800 mb-3">{t('ota.deployments')}</h2>
      <div className="bg-white rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.deployments.device')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.deployments.status')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.deployments.assigned')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('ota.deployments.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {deployments.map((dep) => {
              const dev = devices.find((d) => d.id === dep.device_id)
              return (
                <tr key={dep.id}>
                  <td className="px-4 py-2">{dev?.name || dep.device_id}</td>
                  <td className="px-4 py-2">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', statusColors[dep.status] || '')}>
                      {dep.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(dep.assigned_at)}</td>
                  <td className="px-4 py-2">
                    {dep.status === 'pending' && (
                      <button
                        onClick={async () => { await cancelDeployment(dep.id); load() }}
                        className="text-red-600 hover:underline text-xs"
                      >
                        {t('ota.deployments.cancel')}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <Pagination offset={depOffset} limit={PAGE_SIZE} total={depTotal} onPageChange={setDepOffset} />
    </div>
  )
}
