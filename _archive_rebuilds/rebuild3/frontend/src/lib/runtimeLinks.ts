export function launcherUrl(): string {
  const port = import.meta.env.VITE_LAUNCHER_PORT || '47120';
  if (typeof window === 'undefined') {
    return `http://127.0.0.1:${port}`;
  }
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}
