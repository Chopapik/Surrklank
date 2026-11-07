import { useLaboratory } from './features/laboratory/useLaboratory';
import { stateLabels } from './features/laboratory/laboratory.types';
import { useDeviceControls } from './features/application/useDeviceControls';

const controlStyle =
  '[font:inherit] p-[8px] [margin:6px_8px_6px_0] text-black bg-white ' +
  '[border:2px_outset_#fff] rounded-none disabled:text-[#666] disabled:bg-[#ddd]';
const sectionStyle = 'py-[18px] [border-top:1px_solid_#fff] mt-[20px]';
const preStyle = 'whitespace-pre-wrap [overflow-wrap:anywhere]';

export function App() {
  const laboratory = useLaboratory();
  const { sendAction, atx, connectionState, firmwareState, busy, busyReason, pingText } = useDeviceControls();
  const { connection, ready, connected, statusLabel, socketLabel } = connectionState;
  const { firmware, ports, selectedPort, setSelectedPort, requestUpload, error, uploadPending } = firmwareState;

  return (
    <>
      <h1>Surrklank</h1>
      <small className="block min-h-[1.2em]">{socketLabel}</small>

      <section className={sectionStyle}>
        <h2 className="text-[20px] min-h-[1.2em]">{statusLabel}</h2>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => sendAction('connect')}>
          Połącz
        </button>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => sendAction('disconnect')}>
          Rozłącz
        </button>
        <button className={controlStyle} disabled={!ready || busy || !connected} onClick={() => sendAction('ping')}>
          Ping
        </button>
        <p>{pingText}</p>
        <p className="text-white">{error || firmware.error || connection?.error || ''}</p>
        <small>Ostatni odczyt firmware</small>
        <pre className={preStyle}>{connection?.device ? JSON.stringify(connection.device, null, 2) : ''}</pre>
      </section>

      <section className={sectionStyle}>
        <h2 className="text-[20px]">Zasilanie ATX</h2>
        <button className={controlStyle} role="switch" aria-label="Zasilanie ATX"
          aria-checked={atx.on === true} aria-describedby={busyReason ? 'device-busy-reason' : undefined}
          disabled={atx.on === null || busy || atx.pending}
          onClick={() => atx.setState(atx.on ? 'off' : 'on')}>
          {atx.on === null ? 'Stan nieznany' : atx.on ? 'ATX włączony' : 'ATX wyłączony'}
        </button>
        {busyReason && <p id="device-busy-reason" role="status">{busyReason}</p>}
        <small>Stan wyjścia ESP32 sterującego tranzystorem, bez pomiaru napięcia.</small>
        {atx.error && <p role="alert">{atx.error}</p>}
      </section>

      <section className={sectionStyle}>
        <h2 className="text-[20px]">Laboratorium FDD</h2>
        <p>1–300 Hz · 1–60000 ms · Uruchom najpierw parkuje i sprawdza całą paczkę. Po upływie czasu głowica zostaje w miejscu. Ręczny Stop parkuje na TRACK0.</p>
        {!laboratory.snapshot.supported && <p>Połącz firmware obsługujący Laboratorium.</p>}
        <table className="w-full text-left">
          <thead><tr><th>Wybór</th><th>Hz</th><th>Czas [ms]</th><th>Stan</th><th>Ostatni TRACK0</th><th></th></tr></thead>
          <tbody>{laboratory.devices.map((entry) => {
            const state = laboratory.snapshot.devices.find((device) => device.device === entry.device);
            const available = ready && connected && laboratory.snapshot.available && !firmware.busy && !uploadPending;
            return <tr key={entry.device}>
              <td><label><input type="checkbox" checked={entry.selected} onChange={(event) => laboratory.update(entry.device, { selected: event.target.checked })} /> FDD {entry.device}</label></td>
              <td><input className={controlStyle + ' w-[100px]'} aria-label={`Hz FDD ${entry.device}`} type="number" min="1" max="300" step="0.001" value={entry.frequency_hz} onChange={(event) => laboratory.update(entry.device, { frequency_hz: Number(event.target.value) })} /></td>
              <td><input className={controlStyle + ' w-[110px]'} aria-label={`Czas FDD ${entry.device}`} type="number" min="1" max="60000" value={entry.duration_ms} onChange={(event) => laboratory.update(entry.device, { duration_ms: Number(event.target.value) })} /></td>
              <td>{stateLabels[state?.state ?? 'unknown']}{state?.message && <span> · {state.message}</span>}</td>
              <td>{state?.track0 == null ? '?' : state.track0 ? 'Tak' : 'Nie'}</td>
              <td><button className={controlStyle} disabled={!available || laboratory.stopping} onClick={() => laboratory.stop(entry.device)}>Stop FDD {entry.device}</button></td>
            </tr>;
          })}</tbody>
        </table>
        <button className={controlStyle} disabled={!ready || !connected || !laboratory.snapshot.available || !laboratory.snapshot.supported || firmware.busy || uploadPending || laboratory.pending || !laboratory.devices.some((device) => device.selected)} onClick={laboratory.start}>Uruchom zaznaczone FDD</button>
        <button className={controlStyle} disabled={!ready || !connected || !laboratory.snapshot.available || firmware.busy || uploadPending || laboratory.stopping} onClick={() => laboratory.stop(undefined)}>Stop wszystkie FDD</button>
        {laboratory.error && <p role="alert">{laboratory.error}</p>}
        <p>Licznik STEP i pozycja szacowana nie potwierdzają rzeczywistej liczby kroków głowicy.</p>
        <details><summary>Dane Laboratorium</summary><pre className={preStyle}>{JSON.stringify(laboratory.snapshot, null, 2)}</pre></details>
      </section>

      <section className={sectionStyle}>
        <h2 className="text-[20px] min-h-[1.2em]">Firmware</h2>
        <select className={controlStyle} value={selectedPort} onChange={(event) => setSelectedPort(event.target.value)}>
          {ports.map((port) => <option key={port.port} value={port.port}>{port.port}</option>)}
        </select>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => requestUpload('usb')}>
          Kompiluj i wgraj przez USB
        </button>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => requestUpload('ota')}>
          Kompiluj i wgraj przez BLE OTA
        </button>
        <p>{firmware.stage}</p>
        <progress className="w-full accent-white" max="100" value={firmware.progress ?? 0} />
        <pre className={preStyle}>{firmware.result ? JSON.stringify(firmware.result, null, 2) : ''}</pre>
      </section>
    </>
  );
}
