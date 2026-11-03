// Create an offline, dedicated template; never open or modify an existing project.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security;
using System.Web.Script.Serialization;
using Siemens.Engineering;
using Siemens.Engineering.Compiler;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;

internal static class SimulationTemplate
{
    internal static int List(string filter)
    {
        Console.Error.WriteLine("Starting TIA Portal for catalog query");
        using (var portal = TiaSession.Start())
        {
            Console.Error.WriteLine("Querying installed CPU catalog: " + filter);
            var entries = portal.HardwareCatalog.Find(filter).Select(e => new
            {
                name = e.TypeName, article_number = e.ArticleNumber,
                type_identifier = e.TypeIdentifier, version = e.Version
            }).ToArray();
            Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer().Serialize(new { status = "catalog_listed", entries }));
        }
        return 0;
    }

    internal static int Create(string requestFile)
    {
        var json = new JavaScriptSerializer();
        var request = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(requestFile));
        string root = Path.GetFullPath((string)request["directory"]);
        string name = (string)request["name"];
        string type = (string)request["type_identifier"];
        string protection = request.ContainsKey("configuration_protection") ? (string)request["configuration_protection"] : "password";
        if (protection != "password" && protection != "none")
            throw new InvalidDataException("Expected configuration_protection=password or none");
        var credentials = json.Deserialize<Dictionary<string, string>>(File.ReadAllText(Path.GetFullPath((string)request["credentials_file"])));
        if (name != Path.GetFileName(name) || string.IsNullOrWhiteSpace(name) || name == "." || name == "..")
            throw new InvalidDataException("Expected a single project name");
        if (!type.StartsWith("OrderNumber:6ES7 51", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Use a standard S7-1500 CPU catalog identifier");
        string destination = Path.Combine(root, name);
        if (File.Exists(destination) || Directory.Exists(destination))
            throw new IOException("Refusing to overwrite an existing template: " + destination);
        Directory.CreateDirectory(root);
        Console.Error.WriteLine("Starting TIA Portal to create offline simulation template");
        using (var portal = TiaSession.Start())
        {
            Console.Error.WriteLine("Creating project with catalog identifier: " + type);
            var project = portal.Projects.Create(new DirectoryInfo(root), name);
            try
            {
                project.Devices.CreateWithItem(type, "PLC_1", "WB_S7_1500");
                var settings = project.GetService<PlcSimulationSettingsProvider>();
                if (settings == null) throw new InvalidOperationException("No simulation settings service");
                settings.IsSimulationDuringBlockCompilationEnabled = true;
                DeviceItem cpu;
                var plc = CompileJob.FindPlcSoftware(project, out cpu);
                if (plc == null) throw new InvalidOperationException("Created device has no PLC software");
                // Only configure this newly created offline CPU. The folder-card
                // route cannot provision PLCSIM's Windows-user-bound master secret.
                // An explicitly requested simulation-only template may omit that
                // protection while retaining the CPU's restricted access level.
                using (var fullAccess = Secure(credentials["full_access_password"]))
                    cpu.GetService<PlcAccessLevelProvider>().SetPassword(PlcProtectionAccessLevel.FullAccess, fullAccess);
                var secret = cpu.GetService<PlcMasterSecretConfigurator>();
                if (protection == "none") secret.Unprotect();
                else using (var configuration = Secure(credentials["configuration_password"]))
                    secret.Protect(configuration);
                var hardwareCompiler = cpu.GetService<ICompilable>();
                if (hardwareCompiler == null) throw new InvalidOperationException("No CPU hardware compiler");
                var hardware = hardwareCompiler.Compile();
                var hardwareMessages = new List<object>();
                CompileJob.CollectMessages(hardware.Messages, hardwareMessages);
                var result = plc.GetService<ICompilable>().Compile();
                project.Save();
                var receipt = new
                {
                    status = result.ErrorCount + hardware.ErrorCount == 0 ? "template_created" : "template_compile_failed",
                    project = Path.Combine(destination, name + ".ap21"),
                    type_identifier = type,
                    configuration_protection = secret.MasterSecretConfiguration.ToString(),
                    simulation_support = settings.IsSimulationDuringBlockCompilationEnabled,
                    errors = result.ErrorCount + hardware.ErrorCount,
                    warnings = result.WarningCount + hardware.WarningCount,
                    hardware_diagnostics = hardwareMessages,
                    messages = result.Messages.Select(m => new { state = m.State.ToString(), text = m.Description }).ToArray(),
                    scope = "Offline template only; no PLCSIM runtime or license claim"
                };
                File.WriteAllText(Path.Combine(destination, "workbench-template.json"), json.Serialize(receipt));
                Console.WriteLine("WB_RESULT_JSON=" + json.Serialize(receipt));
                return result.ErrorCount + hardware.ErrorCount == 0 ? 0 : 2;
            }
            finally { project.Close(); }
        }
    }

    private static SecureString Secure(string value)
    {
        if (string.IsNullOrEmpty(value) || value.Length < 12) throw new InvalidDataException("Template credential must have at least 12 characters");
        var secure = new SecureString();
        foreach (char character in value) secure.AppendChar(character);
        secure.MakeReadOnly();
        return secure;
    }
}
