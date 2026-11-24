import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleX,
  Copy,
  LoaderCircle,
  RefreshCw,
  Save,
  X,
} from "lucide-react";

import { getNetworkStatus, listModels, saveConfig, testConfig } from "@/api/llm";
import { useRuntimeConfig } from "@/hooks/use-runtime-config";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const ROLE_TABS = [
  { value: "chat", label: "Chat" },
  { value: "extraction", label: "Extraction" },
  { value: "linking", label: "Linking" },
  { value: "embedding", label: "Embedding" },
  { value: "rerank", label: "Rerank" },
];

const ROLE_LABELS = Object.fromEntries(
  ROLE_TABS.map(({ value, label }) => [value, label]),
);

function jsonText(value) {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value ?? {}, null, 2);
}

function parseJsonObject(value, label) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value;
  }

  try {
    const parsed = JSON.parse(typeof value === "string" ? value || "{}" : "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("not an object");
    }
    return parsed;
  } catch {
    throw new Error(`${label} must be a JSON object.`);
  }
}

function Field({ label, htmlFor, hint, className, children }) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function TestResult({ result }) {
  if (!result) {
    return null;
  }

  if (result.ok) {
    const detected = result.detected ?? {};
    const parts = [];
    if (detected.dimensions != null) {
      parts.push(`Dimensions: ${detected.dimensions}`);
    }
    if (detected.supports_json_schema != null) {
      parts.push(
        `JSON schema: ${detected.supports_json_schema ? "supported" : "fallback"}`,
      );
    }
    if (Array.isArray(detected.models_listed) && detected.models_listed.length) {
      parts.push(`Models: ${detected.models_listed.length}`);
    }

    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
        <div className="flex items-center gap-2 font-medium">
          <CheckCircle2 className="size-4" />
          Connection OK · {result.latency_ms} ms
        </div>
        {parts.length > 0 && (
          <p className="mt-1 text-muted-foreground">{parts.join(" · ")}</p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      <div className="flex items-center gap-2 font-medium">
        <CircleX className="size-4" />
        Connection failed
      </div>
      {result.error && <p className="mt-1 break-words">{result.error}</p>}
    </div>
  );
}

function RoleFields({
  role,
  config,
  apiKeyValue,
  apiKeySet,
  apiKeyDirty,
  onFieldChange,
  onApiKeyChange,
  onClearApiKey,
  onCopyFromChat,
  onFetchModels,
  modelOptions,
  modelsError,
  onTest,
  testing,
  testResult,
}) {
  const isRerank = role === "rerank";
  const isEmbedding = role === "embedding";
  const supportsValue =
    config.supports_json_schema === true
      ? "on"
      : config.supports_json_schema === false
        ? "off"
        : "auto";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">{ROLE_LABELS[role]}</h3>
        <div className="flex flex-wrap gap-2">
          {role !== "chat" && (
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => onCopyFromChat(role)}
            >
              <Copy className="mr-2 size-4" />
              Copy from chat
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            type="button"
            onClick={() => onTest(role)}
            disabled={testing}
          >
            {testing ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : null}
            {testing ? "Testing…" : "Test connection"}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Base URL" htmlFor={`${role}-base-url`} className="md:col-span-2">
          <Input
            id={`${role}-base-url`}
            type="url"
            value={config.base_url ?? ""}
            onChange={(event) => onFieldChange(role, "base_url", event.target.value)}
            placeholder="http://127.0.0.1:8000/v1"
            autoComplete="off"
          />
        </Field>

        <Field label="Model" htmlFor={`${role}-model`}>
          <div className="flex gap-2">
            <Input
              id={`${role}-model`}
              type="text"
              list={`${role}-model-options`}
              value={config.model ?? ""}
              onChange={(event) => onFieldChange(role, "model", event.target.value)}
              placeholder="Enter a model ID"
              autoComplete="off"
            />
            <Button
              variant="outline"
              size="icon"
              type="button"
              title="Fetch models"
              onClick={() => onFetchModels(role)}
            >
              <RefreshCw className="size-4" />
            </Button>
          </div>
          <datalist id={`${role}-model-options`}>
            {(modelOptions ?? []).map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
          {modelsError ? <p className="text-xs text-destructive">{modelsError}</p> : null}
        </Field>

        <Field label="API key" htmlFor={`${role}-api-key`}>
          <div className="flex gap-2">
            <Input
              id={`${role}-api-key`}
              type="password"
              value={apiKeyValue}
              onChange={(event) => onApiKeyChange(role, event.target.value)}
              placeholder={apiKeySet ? "Saved key" : "Enter API key"}
              autoComplete="new-password"
            />
            {apiKeySet && (
              <Button
                variant="outline"
                size="icon"
                type="button"
                title="Clear saved key"
                onClick={() => onClearApiKey(role)}
              >
                <X className="size-4" />
              </Button>
            )}
          </div>
          {apiKeyDirty && (
            <p className="text-xs text-muted-foreground">Key will be replaced on save.</p>
          )}
        </Field>
      </div>

      {isRerank ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Mode" htmlFor={`${role}-mode`}>
            <Select
              value={config.mode ?? "none"}
              onValueChange={(next) => onFieldChange(role, "mode", next)}
            >
              <SelectTrigger id={`${role}-mode`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="endpoint">Endpoint</SelectItem>
                <SelectItem value="llm">LLM</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Top N" htmlFor={`${role}-top-n`}>
            <Input
              id={`${role}-top-n`}
              type="number"
              min={1}
              value={config.top_n ?? 10}
              onChange={(event) =>
                onFieldChange(
                  role,
                  "top_n",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </Field>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Temperature" htmlFor={`${role}-temperature`}>
              <div className="flex items-center gap-3">
                <Slider
                  id={`${role}-temperature`}
                  min={0}
                  max={2}
                  step={0.1}
                  value={[Number(config.temperature ?? 0)]}
                  onValueChange={([value]) => onFieldChange(role, "temperature", value)}
                />
                <span className="w-10 text-right text-sm tabular-nums text-muted-foreground">
                  {Number(config.temperature ?? 0).toFixed(1)}
                </span>
              </div>
            </Field>

            <Field label="Max tokens" htmlFor={`${role}-max-tokens`}>
              <Input
                id={`${role}-max-tokens`}
                type="number"
                min={1}
                value={config.max_tokens ?? ""}
                onChange={(event) =>
                  onFieldChange(
                    role,
                    "max_tokens",
                    event.target.value === "" ? "" : Number(event.target.value),
                  )
                }
              />
            </Field>

            <Field label="Timeout (seconds)" htmlFor={`${role}-timeout`}>
              <Input
                id={`${role}-timeout`}
                type="number"
                min={1}
                step={0.1}
                value={config.timeout_s ?? ""}
                onChange={(event) =>
                  onFieldChange(
                    role,
                    "timeout_s",
                    event.target.value === "" ? "" : Number(event.target.value),
                  )
                }
              />
            </Field>

            <Field label="JSON schema support" htmlFor={`${role}-supports-json-schema`}>
              <Select
                value={supportsValue}
                onValueChange={(next) =>
                  onFieldChange(
                    role,
                    "supports_json_schema",
                    next === "auto" ? null : next === "on",
                  )
                }
              >
                <SelectTrigger id={`${role}-supports-json-schema`} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect</SelectItem>
                  <SelectItem value="on">Supported</SelectItem>
                  <SelectItem value="off">Fallback</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>

          <Field
            label="System instructions"
            htmlFor={`${role}-system-instructions`}
            className="md:col-span-2"
          >
            <Textarea
              id={`${role}-system-instructions`}
              value={config.system_instructions ?? ""}
              onChange={(event) =>
                onFieldChange(role, "system_instructions", event.target.value)
              }
              className="min-h-28"
            />
          </Field>

          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label="Extra headers"
              htmlFor={`${role}-extra-headers`}
              className="md:col-span-2"
            >
              <Textarea
                id={`${role}-extra-headers`}
                value={jsonText(config.extra_headers)}
                onChange={(event) =>
                  onFieldChange(role, "extra_headers", event.target.value)
                }
                className="min-h-24 font-mono text-xs"
                placeholder='{"X-Trace": "value"}'
              />
            </Field>

            <Field
              label="Extra body"
              htmlFor={`${role}-extra-body`}
              className="md:col-span-2"
            >
              <Textarea
                id={`${role}-extra-body`}
                value={jsonText(config.extra_body)}
                onChange={(event) =>
                  onFieldChange(role, "extra_body", event.target.value)
                }
                className="min-h-24 font-mono text-xs"
                placeholder='{"some_option": true}'
              />
            </Field>
          </div>
        </>
      )}

      {isEmbedding && (
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Dimensions" htmlFor={`${role}-dimensions`}>
            <Input
              id={`${role}-dimensions`}
              type="number"
              min={1}
              value={config.dimensions ?? ""}
              onChange={(event) =>
                onFieldChange(
                  role,
                  "dimensions",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </Field>

          <Field label="Batch size" htmlFor={`${role}-batch-size`}>
            <Input
              id={`${role}-batch-size`}
              type="number"
              min={1}
              value={config.batch_size ?? 32}
              onChange={(event) =>
                onFieldChange(
                  role,
                  "batch_size",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </Field>

          <Field label="Query prefix" htmlFor={`${role}-query-prefix`}>
            <Input
              id={`${role}-query-prefix`}
              value={config.query_prefix ?? ""}
              onChange={(event) =>
                onFieldChange(role, "query_prefix", event.target.value)
              }
            />
          </Field>

          <Field label="Document prefix" htmlFor={`${role}-document-prefix`}>
            <Input
              id={`${role}-document-prefix`}
              value={config.document_prefix ?? ""}
              onChange={(event) =>
                onFieldChange(role, "document_prefix", event.target.value)
              }
            />
          </Field>
        </div>
      )}

      <TestResult result={testResult} />
    </div>
  );
}

export default function Settings() {
  const queryClient = useQueryClient();
  const { data: config, isLoading, error: loadError, refetch } = useRuntimeConfig();
  const { data: networkStatus } = useQuery({
    queryKey: ["network-status"],
    queryFn: getNetworkStatus,
    retry: false,
  });

  const [activeTab, setActiveTab] = useState("chat");
  const [draft, setDraft] = useState(null);
  const [apiKeyValues, setApiKeyValues] = useState({});
  const [apiKeyDirty, setApiKeyDirty] = useState({});
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState({ status: "idle", message: "" });
  const [testResults, setTestResults] = useState({});
  const [testingRole, setTestingRole] = useState(null);
  const [modelOptions, setModelOptions] = useState({});
  const [modelsError, setModelsError] = useState({});

  useEffect(() => {
    if (config && draft === null) {
      setDraft(config);
      setDirty(false);
    }
  }, [config, draft]);

  function updateRole(role, patch) {
    setDraft((current) => ({
      ...current,
      [role]: {
        ...current[role],
        ...patch,
      },
    }));
    setDirty(true);
    setSaveState({ status: "idle", message: "" });
  }

  function updateGlobal(patch) {
    setDraft((current) => ({
      ...current,
      ...patch,
    }));
    setDirty(true);
    setSaveState({ status: "idle", message: "" });
  }

  function handleFieldChange(role, field, value) {
    updateRole(role, { [field]: value });
  }

  function handleApiKeyChange(role, value) {
    setApiKeyValues((current) => ({ ...current, [role]: value }));
    setApiKeyDirty((current) => ({ ...current, [role]: true }));
    setDirty(true);
    setSaveState({ status: "idle", message: "" });
  }

  function handleClearApiKey(role) {
    handleApiKeyChange(role, "");
  }

  function handleCopyFromChat(role) {
    updateRole(role, {
      base_url: draft.chat.base_url,
      model: draft.chat.model,
    });
  }

  async function handleTest(role) {
    setTestingRole(role);
    setTestResults((current) => ({ ...current, [role]: undefined }));
    try {
      const result = await testConfig(role);
      setTestResults((current) => ({ ...current, [role]: result }));
    } catch (error) {
      setTestResults((current) => ({
        ...current,
        [role]: {
          role,
          ok: false,
          latency_ms: null,
          error: error instanceof Error ? error.message : "Connection failed",
          detected: {},
        },
      }));
    } finally {
      setTestingRole(null);
    }
  }

  async function handleFetchModels(role) {
    setModelsError((current) => ({ ...current, [role]: "" }));
    try {
      const result = await listModels(role);
      setModelOptions((current) => ({
        ...current,
        [role]: result.models ?? [],
      }));
    } catch (error) {
      setModelsError((current) => ({
        ...current,
        [role]: error instanceof Error ? error.message : "Could not fetch models.",
      }));
    }
  }

  function buildSavePayload(current, keyValues, keyDirty) {
    const payload = {};

    for (const role of ROLE_TABS.map((tab) => tab.value)) {
      const roleConfig = current[role];
      const rolePayload = { ...roleConfig };
      delete rolePayload.api_key_set;
      delete rolePayload.api_key;

      if (role !== "rerank") {
        rolePayload.extra_headers = parseJsonObject(
          rolePayload.extra_headers,
          "Extra headers",
        );
        rolePayload.extra_body = parseJsonObject(rolePayload.extra_body, "Extra body");
      }

      if (keyDirty[role]) {
        rolePayload.api_key = keyValues[role]?.trim() ? keyValues[role] : null;
      }
      payload[role] = rolePayload;
    }

    payload.concurrency = Number(current.concurrency || 4);
    payload.token_budget_per_job =
      current.token_budget_per_job === "" || current.token_budget_per_job == null
        ? null
        : Number(current.token_budget_per_job);

    return payload;
  }

  async function handleSave() {
    setSaveState({ status: "saving", message: "" });
    try {
      const payload = buildSavePayload(draft, apiKeyValues, apiKeyDirty);
      const saved = await saveConfig(payload);
      queryClient.setQueryData(["runtime-config"], saved);
      setDraft(saved);
      setApiKeyValues({});
      setApiKeyDirty({});
      setDirty(false);
      setSaveState({ status: "success", message: "Settings saved." });
    } catch (error) {
      setSaveState({
        status: "error",
        message: error instanceof Error ? error.message : "Could not save settings.",
      });
    }
  }

  const remoteRoles = (networkStatus?.roles ?? []).filter((entry) => !entry.local);
  const isSaving = saveState.status === "saving";

  if (isLoading) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-96 w-full" />
      </section>
    );
  }

  if (loadError || !draft) {
    return (
      <section className="mx-auto max-w-4xl">
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-4 text-sm text-destructive">
          <p className="font-medium">Could not load configuration.</p>
          {loadError ? <p className="mt-1">{loadError.message}</p> : null}
          <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Settings</h2>
          <p className="mt-1 text-muted-foreground">Model roles and job limits.</p>
        </div>

        <Button onClick={handleSave} disabled={!dirty || isSaving}>
          {isSaving ? (
            <LoaderCircle className="mr-2 size-4 animate-spin" />
          ) : (
            <Save className="mr-2 size-4" />
          )}
          {isSaving ? "Saving…" : "Save"}
        </Button>
      </div>

      {dirty && <p className="text-sm text-muted-foreground">Unsaved changes.</p>}

      {saveState.message && (
        <p
          className={cn(
            "text-sm",
            saveState.status === "error"
              ? "text-destructive"
              : "text-emerald-600 dark:text-emerald-400",
          )}
        >
          {saveState.message}
        </p>
      )}

      {config.keychain?.warning && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          {config.keychain.warning}
        </div>
      )}

      {remoteRoles.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          <p className="font-medium">Some endpoints are not local</p>
          <p className="mt-1">
            Model traffic for {remoteRoles.map((entry) => entry.role).join(", ")} leaves
            this device.
          </p>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Model roles</CardTitle>
          <CardDescription>Endpoint, model, and request settings.</CardDescription>
        </CardHeader>

        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="flex w-full justify-start overflow-x-auto">
              {ROLE_TABS.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {ROLE_TABS.map((tab) => (
              <TabsContent key={tab.value} value={tab.value}>
                <RoleFields
                  role={tab.value}
                  config={draft[tab.value]}
                  apiKeyValue={apiKeyValues[tab.value] ?? ""}
                  apiKeySet={Boolean(draft[tab.value].api_key_set)}
                  apiKeyDirty={Boolean(apiKeyDirty[tab.value])}
                  onFieldChange={handleFieldChange}
                  onApiKeyChange={handleApiKeyChange}
                  onClearApiKey={handleClearApiKey}
                  onCopyFromChat={handleCopyFromChat}
                  onFetchModels={handleFetchModels}
                  modelOptions={modelOptions[tab.value] ?? []}
                  modelsError={modelsError[tab.value] ?? ""}
                  onTest={handleTest}
                  testing={testingRole === tab.value}
                  testResult={testResults[tab.value]}
                />
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>Job concurrency and token budget.</CardDescription>
        </CardHeader>

        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Concurrency" htmlFor="concurrency">
            <Input
              id="concurrency"
              type="number"
              min={1}
              value={draft.concurrency ?? ""}
              onChange={(event) =>
                updateGlobal({
                  concurrency:
                    event.target.value === "" ? "" : Number(event.target.value),
                })
              }
            />
          </Field>

          <Field label="Token budget per job" htmlFor="token-budget">
            <Input
              id="token-budget"
              type="number"
              min={0}
              value={draft.token_budget_per_job ?? ""}
              placeholder="Unlimited"
              onChange={(event) =>
                updateGlobal({
                  token_budget_per_job:
                    event.target.value === "" ? "" : Number(event.target.value),
                })
              }
            />
          </Field>
        </CardContent>
      </Card>
    </section>
  );
}
