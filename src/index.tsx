import {
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { FaCamera } from "react-icons/fa";

interface Settings {
  enabled: boolean;
  interval_ms: number;
  output_path: string;
}

interface CaptureResult {
  ok: boolean;
  path: string | null;
  error: string | null;
}

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[settings: Settings], Settings>("save_settings");
const captureScreenshot = callable<[], CaptureResult>("capture_screenshot");

const MIN_INTERVAL_MS = 1000;

function Content() {
  const [settings, setSettings] = useState<Settings>();
  const [intervalText, setIntervalText] = useState("5000");
  const [status, setStatus] = useState("Loading…");
  const takingScreenshot = useRef(false);

  const persist = async (next: Settings) => {
    const saved = await saveSettings(next);
    setSettings(saved);
    setIntervalText(String(saved.interval_ms));
    return saved;
  };

  const takeScreenshot = useCallback(async () => {
    if (takingScreenshot.current) {
      console.info("Deckshots: skipped tick because a capture is already running");
      return;
    }

    takingScreenshot.current = true;
    setStatus("Capture attempt: requesting a Gamescope screenshot…");

    try {
      const result = await captureScreenshot();
      if (!result.ok || !result.path) {
        throw new Error(result.error || "The backend did not return a screenshot path");
      }
      setStatus(`Saved ${result.path.split("/").pop()}`);
      console.info("Deckshots: capture saved", result.path);
    } catch (error) {
      console.error("Deckshots: capture failed", error);
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Screenshot failed: ${message}`);
    } finally {
      takingScreenshot.current = false;
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    getSettings()
      .then((loaded) => {
        if (!mounted) return;
        setSettings(loaded);
        setIntervalText(String(loaded.interval_ms));
        setStatus(loaded.enabled ? "Automatic screenshots are active" : "Automatic screenshots are off");
      })
      .catch((error) => {
        console.error("Deckshots could not load settings", error);
        if (mounted) setStatus("Could not load settings");
      });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!settings?.enabled) return;

    setStatus("Automatic screenshots are active");
    const timer = window.setInterval(takeScreenshot, settings.interval_ms);
    return () => window.clearInterval(timer);
  }, [settings?.enabled, settings?.interval_ms, takeScreenshot]);

  if (!settings) {
    return <PanelSection title="Deckshots"><PanelSectionRow>{status}</PanelSectionRow></PanelSection>;
  }

  return (
    <PanelSection title="Automatic screenshots">
      <PanelSectionRow>
        <ToggleField
          label="Enabled"
          description="Request a native Gamescope screenshot at the selected interval"
          checked={settings.enabled}
          onChange={async (enabled) => {
            try {
              await persist({ ...settings, enabled });
              setStatus(enabled ? "Automatic screenshots are active" : "Automatic screenshots are off");
            } catch (error) {
              console.error("Deckshots could not save enabled state", error);
              toaster.toast({ title: "Deckshots", body: "Could not save settings" });
            }
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Interval (milliseconds)"
          description={`Minimum ${MIN_INTERVAL_MS} ms`}
          value={intervalText}
          mustBeNumeric
          rangeMin={MIN_INTERVAL_MS}
          onChange={(event) => setIntervalText(event.target.value)}
          onBlur={async () => {
            const parsed = Number.parseInt(intervalText, 10);
            const interval_ms = Number.isFinite(parsed) ? Math.max(MIN_INTERVAL_MS, parsed) : settings.interval_ms;
            try { await persist({ ...settings, interval_ms }); }
            catch (error) {
              console.error("Deckshots could not save interval", error);
              setIntervalText(String(settings.interval_ms));
            }
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Output folder"
          description="Gamescope writes each Deckshots capture here"
          value={settings.output_path}
          onChange={(event) => setSettings({ ...settings, output_path: event.target.value })}
          onBlur={async () => {
            try { await persist(settings); }
            catch (error) {
              console.error("Deckshots could not save output folder", error);
              toaster.toast({ title: "Deckshots", body: "The output folder is not valid" });
              const loaded = await getSettings();
              setSettings(loaded);
            }
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <button onClick={() => void takeScreenshot()}>Capture now</button>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ opacity: 0.75, fontSize: "0.9em" }}>{status}</div>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "Deckshots",
  titleView: <div className={staticClasses.Title}>Deckshots</div>,
  content: <Content />,
  icon: <FaCamera />,
  alwaysRender: true,
  onDismount() { console.log("Deckshots unloaded"); },
}));
