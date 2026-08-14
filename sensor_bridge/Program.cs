using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using LibreHardwareMonitor.Hardware;

namespace KindleMonitor.SensorBridge
{
    internal sealed class UpdateVisitor : IVisitor
    {
        public void VisitComputer(IComputer computer)
        {
            computer.Traverse(this);
        }

        public void VisitHardware(IHardware hardware)
        {
            hardware.Update();
            foreach (IHardware subHardware in hardware.SubHardware)
            {
                subHardware.Accept(this);
            }
        }

        public void VisitSensor(ISensor sensor) { }
        public void VisitParameter(IParameter parameter) { }
    }

    internal static class Program
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        private static IEnumerable<IHardware> WalkHardware(IEnumerable<IHardware> hardwareItems)
        {
            foreach (IHardware hardware in hardwareItems)
            {
                yield return hardware;
                foreach (IHardware child in WalkHardware(hardware.SubHardware))
                {
                    yield return child;
                }
            }
        }

        private static object TakeSnapshot(Computer computer)
        {
            computer.Accept(new UpdateVisitor());
            var sensors = new List<Dictionary<string, object>>();

            foreach (IHardware hardware in WalkHardware(computer.Hardware))
            {
                foreach (ISensor sensor in hardware.Sensors)
                {
                    if (!sensor.Value.HasValue || float.IsNaN(sensor.Value.Value))
                    {
                        continue;
                    }

                    sensors.Add(new Dictionary<string, object>
                    {
                        { "hardware_type", hardware.HardwareType.ToString() },
                        { "hardware_name", hardware.Name },
                        { "hardware_id", hardware.Identifier.ToString() },
                        { "sensor_type", sensor.SensorType.ToString() },
                        { "sensor_name", sensor.Name },
                        { "sensor_id", sensor.Identifier.ToString() },
                        { "value", Math.Round(sensor.Value.Value, 3) }
                    });
                }
            }

            return new Dictionary<string, object>
            {
                { "ok", true },
                { "timestamp", DateTimeOffset.UtcNow.ToUnixTimeSeconds() },
                { "sensors", sensors }
            };
        }

        private static int Main(string[] args)
        {
            bool once = false;
            int intervalMs = 2000;

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--once")
                {
                    once = true;
                }
                else if (args[i] == "--interval-ms" && i + 1 < args.Length)
                {
                    int parsed;
                    if (int.TryParse(args[++i], NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed))
                    {
                        intervalMs = Math.Max(500, parsed);
                    }
                }
            }

            try
            {
                var computer = new Computer
                {
                    IsCpuEnabled = true,
                    IsGpuEnabled = true,
                    IsMemoryEnabled = true,
                    IsMotherboardEnabled = true,
                    IsStorageEnabled = true,
                    IsControllerEnabled = true,
                    IsNetworkEnabled = true,
                    IsPsuEnabled = true
                };
                computer.Open();
                try
                {
                    do
                    {
                        Console.WriteLine(Json.Serialize(TakeSnapshot(computer)));
                        Console.Out.Flush();
                        if (!once)
                        {
                            Thread.Sleep(intervalMs);
                        }
                    }
                    while (!once);
                }
                finally
                {
                    computer.Close();
                }
                return 0;
            }
            catch (Exception exception)
            {
                var error = new Dictionary<string, object>
                {
                    { "ok", false },
                    { "error", exception.GetType().Name },
                    { "message", exception.Message }
                };
                Console.WriteLine(Json.Serialize(error));
                return 1;
            }
        }
    }
}
