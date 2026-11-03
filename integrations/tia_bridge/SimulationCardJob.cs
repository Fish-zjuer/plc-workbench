// API-only worker. It never initializes TIA Portal in this process.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;

internal sealed class SimulationCardJob
{
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };
    private string evidence;
    private static void Emit(object value) { Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 }.Serialize(value)); }
    private void CheckCancel() { if (File.Exists(Path.Combine(evidence, "cancel.signal"))) throw new OperationCanceledException("Simulation cancelled"); }

    public int Run(string requestPath)
    {
        var request = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(requestPath));
        if ((string)request["schema"] != "tia-simulation-v1") throw new InvalidDataException("Unknown simulation protocol");
        evidence = (string)request["evidence_directory"];
        CheckCancel();
        if (AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetName().Name.StartsWith("Siemens.Engineering.", StringComparison.Ordinal)))
            throw new InvalidOperationException("The runtime host must not load Openness assemblies");
        var prepared = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(evidence, "prepared_card.json")));
        var fingerprint = (Dictionary<string, object>)request["execution_fingerprint"];
        if ((string)prepared["schema"] != "tia-prepared-card-v1" ||
            (string)prepared["source_sha256"] != (string)request["source_sha256"] ||
            (string)prepared["source_bundle_sha256"] != FileHash((string)request["source"]) ||
            (string)prepared["bridge_sha256"] != (string)fingerprint["bridge_sha256"] ||
            (string)prepared["runtime_host_sha256"] != (string)fingerprint["runtime_host_sha256"] ||
            (string)prepared["runtime_host_sha256"] != FileHash(Assembly.GetExecutingAssembly().Location))
            throw new InvalidDataException("Prepared card identity does not match source or bridge");
        string exported = Path.Combine(evidence, "virtual_memory_card");
        var expected = (Dictionary<string, object>)prepared["card_sha256"];
        var actual = HashTree(exported);
        if (actual.Count != expected.Count || actual.Any(kv => !expected.ContainsKey(kv.Key) || (string)expected[kv.Key] != kv.Value))
            throw new InvalidDataException("Prepared card content changed after export");
        var api = new SimulationApi((string)request["simulation_api"]);
        string instanceName = "WB_" + Guid.NewGuid().ToString("N");
        string card = Path.Combine(api.DefaultStoragePath, instanceName, "SIMATIC_MC");
        if (Directory.Exists(Path.GetDirectoryName(card))) throw new IOException("Instance storage already exists");
        CopyDirectory(exported, card);
        object instance = null;
        string cpuArticle = (string)prepared["cpu_order_number"];
        string powerOnStatus = "not_executed";
        var startup = Stopwatch.StartNew();
        try
        {
            CheckCancel();
            instance = api.Register(instanceName, cpuArticle);
            Console.Error.WriteLine("Starting owned PLCSIM instance: " + instanceName);
            File.WriteAllText(Path.Combine(evidence, "simulator.json"), json.Serialize(new { owned_by = "plc-workbench", instance_name = instanceName, simulation_api = request["simulation_api"], memory_card = card }));
            startup.Restart();
            SaveRuntime(api, instance, "power_on_pending", powerOnStatus, startup.Elapsed.TotalSeconds);
            // This bounds firmware startup; the trial confirmation retains its
            // independent vendor deadline and still requires manual action.
            powerOnStatus = Convert.ToString(api.Invoke(instance, "PowerOn", (uint)180000), CultureInfo.InvariantCulture);
            SaveRuntime(api, instance, "powered_on", powerOnStatus, startup.Elapsed.TotalSeconds);
            string readyState = api.Property(instance, "OperatingState").ToString();
            if (!new[] { "Stop", "Run", "Freeze", "Hold" }.Contains(readyState))
                throw new InvalidOperationException("PLCSIM did not reach a ready state: " + readyState);
            CheckCancel();
            api.Invoke(instance, "UpdateTagList");
            api.Invoke(instance, "Run", (uint)60000);
            string db = (string)request["result_db"];
            var timer = Stopwatch.StartNew();
            double timeout = Convert.ToDouble(request["simulation_timeout_seconds"], CultureInfo.InvariantCulture);
            while (!(bool)api.Invoke(instance, "ReadBool", db + ".WB_Done"))
            {
                CheckCancel();
                if (timer.Elapsed.TotalSeconds > timeout) throw new TimeoutException("Siemens test harness did not finish");
                Thread.Sleep(20);
            }
            var names = ((IEnumerable)request["output_names"]).Cast<string>().ToArray();
            var types = ((IEnumerable)request["output_types"]).Cast<string>().ToArray();
            int count = Convert.ToInt32(request["row_count"], CultureInfo.InvariantCulture);
            var rows = new List<object>(); var times = new List<int>();
            for (int r = 0; r < count; r++)
            {
                CheckCancel(); var row = new Dictionary<string, object>();
                for (int c = 0; c < names.Length; c++) row[names[c]] = api.Read(instance, db + ".WB_Out" + c + "[" + r + "]", types[c]);
                rows.Add(row); times.Add((int)api.Invoke(instance, "ReadInt32", db + ".WB_ActualMs[" + r + "]"));
            }
            api.Shutdown(instance); instance = null;
            File.WriteAllText(Path.Combine(evidence, "simulator_closed.json"), json.Serialize(new { instance_name = instanceName, powered_off = true, unregistered = true }));
            Emit(new { status = "simulation_completed", simulation = true, instance_name = instanceName, cpu_order_number = cpuArticle, power_on_status = powerOnStatus,
                actual_rows = rows, actual_scan_times_ms = times, platform = "PLCSIM Advanced", scope = "Native finite tests; one FB invocation per supplied row" });
            return 0;
        }
        catch (Exception error)
        {
            if (instance != null) SaveRuntime(api, instance, "failed", powerOnStatus, startup.Elapsed.TotalSeconds, error);
            Emit(new { status = "simulation_error", message = error.ToString(), instance_name = instanceName }); return 2;
        }
        finally
        {
            if (instance != null)
            {
                try
                {
                    api.Shutdown(instance);
                    File.WriteAllText(Path.Combine(evidence, "simulator_closed.json"), json.Serialize(new { instance_name = instanceName, powered_off = true, unregistered = true }));
                }
                catch (Exception error) { Console.Error.WriteLine("Owned simulator cleanup failed: " + error); }
            }
            // Preserve the generated card as evidence; no recursive deletion of runtime storage.
        }
    }

    private static void CopyDirectory(string source, string target)
    {
        Directory.CreateDirectory(target);
        foreach (string file in Directory.GetFiles(source)) File.Copy(file, Path.Combine(target, Path.GetFileName(file)));
        foreach (string child in Directory.GetDirectories(source)) CopyDirectory(child, Path.Combine(target, Path.GetFileName(child)));
    }

    private void SaveRuntime(SimulationApi api, object instance, string phase, string status, double seconds, Exception error = null)
    {
        var snapshot = api.Snapshot(instance);
        snapshot["phase"] = phase;
        snapshot["api_only_process"] = true;
        snapshot["openness_assemblies_loaded"] = AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetName().Name.StartsWith("Siemens.Engineering.", StringComparison.Ordinal));
        snapshot["host_process_id"] = Process.GetCurrentProcess().Id;
        snapshot["power_on_status"] = status;
        snapshot["startup_seconds"] = Math.Round(seconds, 3);
        snapshot["startup_timeout_seconds"] = 180;
        if (error != null) snapshot["error"] = error.ToString();
        File.WriteAllText(Path.Combine(evidence, "simulator_runtime.json"), json.Serialize(snapshot));
    }


    internal static string FileHash(string path)
    {
        using (var algorithm = SHA256.Create())
            return BitConverter.ToString(algorithm.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant();
    }
    internal static Dictionary<string, string> HashTree(string root)
    {
        string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return Directory.GetFiles(root, "*", SearchOption.AllDirectories).ToDictionary(
            path => Path.GetFullPath(path).Substring(prefix.Length).Replace('\\', '/'), path => FileHash(path));
    }
    internal static int Cleanup(string manifest)
    {
        var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(manifest));
        string name = (string)data["instance_name"];
        if ((string)data["owned_by"] != "plc-workbench" || !System.Text.RegularExpressions.Regex.IsMatch(name, "^WB_[0-9a-f]{32}$")) throw new InvalidDataException("Not a workbench-owned simulator");
        var api = new SimulationApi((string)data["simulation_api"]);
        try { api.Shutdown(api.Attach(name)); }
        catch (Exception error) when (SimulationApi.HasRuntimeCode(error, "DoesNotExist"))
        {
            // Cleanup is idempotent, including after a failed startup already
            // unregistered the owned instance in its finally block.
            Console.Error.WriteLine("Owned simulator is already unregistered: " + name);
        }
        return 0;
    }
}

internal sealed class SimulationApi
{
    private readonly Assembly assembly;
    private readonly Type manager;
    private readonly Type instanceType;
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool SetDllDirectory(string path);
    internal SimulationApi(string path)
    {
        if (!SetDllDirectory(Path.GetDirectoryName(Path.GetFullPath(path)))) throw new IOException("Cannot set PLCSIM API dependency path");
        assembly = Assembly.LoadFrom(path);
        manager = assembly.GetType("Siemens.Simatic.Simulation.Runtime.SimulationRuntimeManager", true);
        instanceType = assembly.GetType("Siemens.Simatic.Simulation.Runtime.IInstance", true);
    }
    internal string DefaultStoragePath => (string)manager.GetProperty("DefaultStoragePath").GetValue(null);
    internal object Register(string name, string article)
    {
        string normalized = System.Text.RegularExpressions.Regex.Replace(article, @"\s+", "");
        if (!System.Text.RegularExpressions.Regex.IsMatch(normalized, @"^6ES7\d{3}-[0-9A-Z]{5}-[0-9A-Z]{4}$"))
            throw new InvalidDataException("Expected a standard Siemens CPU article number: " + article);
        // Siemens' article-number overload requires the canonical 19-character
        // order number, including the space after 6ES7. It registers the actual
        // device instead of allocating an unspecified CPU's quantity structure.
        string canonical = normalized.Insert(4, " ");
        return manager.GetMethod("RegisterInstance", new[] { typeof(string), typeof(string) }).Invoke(null, new object[] { canonical, name });
    }
    internal object Attach(string name) => manager.GetMethod("CreateInterface", new[] { typeof(string) }).Invoke(null, new object[] { name });
    internal object Property(object instance, string name) => instanceType.GetProperty(name).GetValue(instance);
    internal Dictionary<string, object> Snapshot(object instance)
    {
        var result = new Dictionary<string, object>();
        foreach (var property in new[] { "OperatingState", "LicenseStatus", "CPUType", "ArticleNumber", "StoragePath" })
        {
            string key = property == "OperatingState" ? "operating_state" : property == "LicenseStatus" ? "license_status" : property == "CPUType" ? "cpu_type" : property == "StoragePath" ? "storage_path" : "article_number";
            try { result[key] = Convert.ToString(Property(instance, property), CultureInfo.InvariantCulture); }
            catch (Exception error) { result[key] = "unavailable: " + error.GetBaseException().Message; }
        }
        return result;
    }
    internal static bool HasRuntimeCode(Exception error, string code)
    {
        var underlying = error.GetBaseException();
        return underlying.GetType().GetProperty("RuntimeErrorCode")?.GetValue(underlying)?.ToString() == code;
    }
    internal object Invoke(object instance, string method, params object[] args)
    {
        var info = instanceType.GetMethod(method, args.Select(x => x.GetType()).ToArray());
        if (info == null) throw new MissingMethodException("PLCSIM API: " + method);
        var result = info.Invoke(instance, args);
        // Siemens documents this PowerOn warning as a successful start under an
        // active trial license. Other warnings and all license errors still fail.
        bool trialStart = method == "PowerOn" && result != null && result.ToString() == "WarningTrialModeActive";
        if (info.ReturnType.Name == "ERuntimeErrorCode" && Convert.ToInt32(result) != 0 && !trialStart) throw new InvalidOperationException(method + ": " + result);
        return result;
    }
    internal object Read(object instance, string tag, string type)
    {
        string method;
        switch (type.ToUpperInvariant())
        {
            case "BOOL": method = "ReadBool"; break;
            case "SINT": method = "ReadInt8"; break;
            case "USINT": case "BYTE": method = "ReadUInt8"; break;
            case "INT": method = "ReadInt16"; break;
            case "UINT": case "WORD": method = "ReadUInt16"; break;
            case "DINT": method = "ReadInt32"; break;
            case "UDINT": case "DWORD": method = "ReadUInt32"; break;
            case "LINT": method = "ReadInt64"; break;
            case "ULINT": case "LWORD": method = "ReadUInt64"; break;
            case "REAL": method = "ReadFloat"; break;
            case "TIME": case "LTIME": case "LREAL": method = "ReadDouble"; break;
            default: throw new NotSupportedException("Native simulation output type: " + type);
        }
        return Invoke(instance, method, tag);
    }
    internal void Shutdown(object instance)
    {
        try
        {
            // A timed-out startup may already be Off. Calling PowerOff in that
            // state throws InvalidOperatingState and used to obscure cleanup.
            if (Property(instance, "OperatingState").ToString() != "Off") Invoke(instance, "PowerOff", (uint)60000);
        }
        finally { try { Invoke(instance, "UnregisterInstance"); } finally { (instance as IDisposable)?.Dispose(); } }
    }
}
