import {
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { FaCamera } from "react-icons/fa";

interface Settings {
  enabled: boolean;
  interval_ms: number;
  output_path: string;
}

interface CopyResult {
  path: string;
}

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[settings: Settings], Settings>("save_settings");
const copyScreenshot = callable<
  [sourcePath: string, appId: number, createdAt: number],
  CopyResult
>("copy_screenshot");

const MIN_INTERVAL_MS = 1000;
const SCREENSHOT_SETTLE_MS = 1200;
// USB HID usage ID for F12. Steam's public typings do not re-export the enum.
const STEAM_SCREENSHOT_KEY = 69;

function Content() {
  const [settings, setSettings] = useState<Settings>();
  const [intervalText, setIntervalText] = useState("5000");
  const [status, setStatus] = useState("Loading…");
  const lastHandle = useRef<number | undefined>(undefined);
  const lastHandleInitialised = useRef(false);
  const takingScreenshot = useRef(false);

  const persist = async (next: Settings) => {
    const saved = await saveSettings(next);
    setSettings(saved);
    setIntervalText(String(saved.interval_ms));
    return saved;
  };

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

    const takeScreenshot = async () => {
      if (takingScreenshot.current) return;
      takingScreenshot.current = true;
      try {
        // Establish a baseline so a failed first keypress cannot copy an old shot.
        if (!lastHandleInitialised.current) {
          try {
            const previous = await SteamClient.Screenshots.GetLastScreenshotTaken();
            lastHandle.current = previous?.hHandle;
          } catch {
            // A user with no screenshots may cause this call to reject.
          }
          lastHandleInitialised.current = true;
        }
        SteamClient.Input.ControllerKeyboardSetKeyState(STEAM_SCREENSHOT_KEY, true);
        SteamClient.Input.ControllerKeyboardSetKeyState(STEAM_SCREENSHOT_KEY, false);
        await new Promise((resolve) => window.setTimeout(resolve, SCREENSHOT_SETTLE_MS));

        const shot = await SteamClient.Screenshots.GetLastScreenshotTaken();
        if (!shot || shot.hHandle === lastHandle.current) {
          setStatus("Steam did not report a new screenshot");
          return;
        }
        lastHandle.current = shot.hHandle;
        const sourcePath = await SteamClient.Screenshots.GetLocalScreenshotPath(shot.nAppID, shot.hHandle);
        const result = await copyScreenshot(sourcePath, shot.nAppID, shot.nCreated);
        setStatus(`Saved ${result.path.split("/").pop()}`);
      } catch (error) {
        console.error("Deckshots capture failed", error);
        setStatus("Screenshot failed; make sure a game and Steam Overlay are running");
      } finally {
        takingScreenshot.current = false;
      }
    };

    setStatus("Automatic screenshots are active");
    const timer = window.setInterval(takeScreenshot, settings.interval_ms);
    return () => window.clearInterval(timer);
  }, [settings?.enabled, settings?.interval_ms]);

  if (!settings) {
    return <PanelSection title="Deckshots"><PanelSectionRow>{status}</PanelSectionRow></PanelSection>;
  }

  return (
    <PanelSection title="Automatic screenshots">
      <PanelSectionRow>
        <ToggleField
          label="Enabled"
          description="Use Steam's screenshot hotkey at the selected interval"
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
          description="Steam keeps its library copy; Deckshots puts another copy here"
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
  onDismount() { console.log("Deckshots unloaded"); },
}));
