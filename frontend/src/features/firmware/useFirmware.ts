import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { listFirmwarePorts, startFirmwareUpload } from './firmware.api';
import {
  firmwarePortsKey,
  firmwareStatusKey,
  initialFirmware,
  type FirmwareTransport,
  type SerialPort,
} from './firmware.types';

const noPorts: SerialPort[] = [];
const isolationQuestion =
  'Czy ESP32 jest podłączone tylko przez USB, a ATX i przewody rejestrów/napędów są odłączone?';

export function useFirmware() {
  const [selectedPort, setSelectedPort] = useState('');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const portsQuery = useQuery({
    queryKey: firmwarePortsKey,
    queryFn: listFirmwarePorts,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  // The WebSocket updates this cache. There is no polling for progress.
  const firmwareQuery = useQuery({
    queryKey: firmwareStatusKey,
    enabled: false,
    initialData: initialFirmware,
    staleTime: Infinity,
  });
  const upload = useMutation({
    mutationFn: (transport: FirmwareTransport) => startFirmwareUpload(transport, selectedPort),
    retry: false,
    onError: (error) => setUploadError(error.message),
  });
  const ports = portsQuery.data ?? noPorts;

  useEffect(() => {
    setSelectedPort((current) =>
      ports.some((port) => port.port === current) ? current : ports[0]?.port ?? '',
    );
  }, [ports]);

  function requestUpload(transport: FirmwareTransport) {
    if (!window.confirm(isolationQuestion)) return;
    setUploadError(null);
    upload.mutate(transport);
  }

  return {
    firmware: firmwareQuery.data,
    ports,
    selectedPort,
    setSelectedPort,
    requestUpload,
    uploadPending: upload.isPending,
    error: uploadError ?? portsQuery.error?.message ?? null,
  };
}
