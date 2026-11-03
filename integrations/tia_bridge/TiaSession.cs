using System;
using Siemens.Engineering;

internal static class TiaSession
{
    internal static TiaPortal Start()
    {
        // Siemens documents that Dispose closes an owned headless instance,
        // whereas a graphical instance remains open after disconnecting. Use
        // headless sessions for repeated agent calls; retain an opt-in UI for
        // interactive diagnostics and demonstrations.
        var mode = Environment.GetEnvironmentVariable("TIA_BRIDGE_WITH_UI") == "1"
            ? TiaPortalMode.WithUserInterface : TiaPortalMode.WithoutUserInterface;
        Console.Error.WriteLine("TIA session mode: " + mode);
        return new TiaPortal(mode);
    }
}
