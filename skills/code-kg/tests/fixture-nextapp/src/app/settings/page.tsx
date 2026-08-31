"use client";

import { useEffect, useState } from "react";
import { loadSettings, saveSettings, defaultSettings } from "@/services/settings";
import { TextField, SelectField, Button, Spinner } from "@/components";
import type { Settings } from "@/shared/types";

const CURRENCIES = [
  { value: "USD", label: "US Dollar" },
  { value: "EUR", label: "Euro" },
  { value: "GBP", label: "Pound" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaultSettings());
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    loadSettings()
      .then((loaded) => {
        if (active) {
          setSettings(loaded);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const update = (patchFields: Partial<Settings>): void => {
    setSettings((prev) => ({ ...prev, ...patchFields }));
    setSaved(false);
  };

  const handleSave = async (): Promise<void> => {
    const next = await saveSettings(settings);
    setSettings(next);
    setSaved(true);
  };

  if (loading) {
    return <Spinner label="Loading settings" />;
  }

  return (
    <main>
      <h1>Settings</h1>
      <TextField
        label="Company name"
        name="companyName"
        value={settings.companyName}
        onChange={(value) => update({ companyName: value })}
      />
      <TextField
        label="Invoice prefix"
        name="invoicePrefix"
        value={settings.invoicePrefix}
        onChange={(value) => update({ invoicePrefix: value })}
      />
      <SelectField
        label="Currency"
        name="currency"
        value={settings.currency}
        options={CURRENCIES}
        onChange={(value) => update({ currency: value })}
      />
      <Button label="Save settings" onClick={() => void handleSave()} />
      {saved ? <p className="form-note">Saved.</p> : null}
    </main>
  );
}
