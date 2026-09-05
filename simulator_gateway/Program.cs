using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace PlcAi.GxSimulator2Gateway
{
    internal sealed class GatewayException : Exception
    {
        public readonly int HttpStatus;
        public readonly string ErrorCode;

        public GatewayException(int httpStatus, string errorCode, string message)
            : base(message)
        {
            HttpStatus = httpStatus;
            ErrorCode = errorCode;
        }
    }

    internal sealed class GatewayConfig
    {
        public readonly int Port;
        public readonly string Token;
        public readonly string ProgId;

        public GatewayConfig()
        {
            Port = ReadInt("GX_SIMULATOR_GATEWAY_PORT", 17831, 1024, 65535);
            Token = (Environment.GetEnvironmentVariable("GX_SIMULATOR_GATEWAY_TOKEN") ?? "").Trim();
            ProgId = (Environment.GetEnvironmentVariable("GX_MX_COMPONENT_PROGID") ?? "").Trim();
            if (Token.Length < 16)
            {
                throw new InvalidOperationException(
                    "GX_SIMULATOR_GATEWAY_TOKEN must contain at least 16 characters."
                );
            }
            if (ProgId.Length > 0 && ProgId.IndexOf("ActProgType", StringComparison.OrdinalIgnoreCase) < 0)
            {
                throw new InvalidOperationException(
                    "Only an ActProgType ProgID is allowed because the route must be fixed to GX Simulator2."
                );
            }
        }

        private static int ReadInt(string name, int fallback, int minimum, int maximum)
        {
            int value;
            string raw = Environment.GetEnvironmentVariable(name);
            if (String.IsNullOrWhiteSpace(raw))
            {
                return fallback;
            }
            if (!Int32.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out value)
                || value < minimum || value > maximum)
            {
                throw new InvalidOperationException(name + " is outside its allowed range.");
            }
            return value;
        }
    }

    internal sealed class MxSimulatorConnection : IDisposable
    {
        // MX Component Version 4/5 constants from Mitsubishi's programming manual.
        // UNIT_SIMULATOR2 proves that this process cannot select a physical PLC route.
        private const int UnitSimulator2 = 0x30;
        private const int CpuFx3UC = 0x208;
        private const int TargetSimulatorForFxCpu = 0;
        private static readonly Regex DevicePattern = new Regex(
            "^(X|Y|M|D|T|C|S)([0-9]+)$",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant
        );

        private readonly string _configuredProgId;
        private dynamic _control;
        private string _activeProgId = "";

        public MxSimulatorConnection(string configuredProgId)
        {
            _configuredProgId = configuredProgId ?? "";
        }

        public bool Connected
        {
            get { return _control != null; }
        }

        public string ActiveProgId
        {
            get { return _activeProgId; }
        }

        public static int SimulatorUnitType
        {
            get { return UnitSimulator2; }
        }

        private IEnumerable<string> CandidateProgIds()
        {
            if (!String.IsNullOrWhiteSpace(_configuredProgId))
            {
                yield return _configuredProgId;
                yield break;
            }
            yield return "ActProgType.ActProgType";
            yield return "ActProgType64.ActProgType64";
        }

        public string FindAvailableProgId()
        {
            foreach (string progId in CandidateProgIds())
            {
                try
                {
                    if (Type.GetTypeFromProgID(progId, false) != null)
                    {
                        return progId;
                    }
                }
                catch (COMException)
                {
                }
            }
            return "";
        }

        public IDictionary<string, object> Connect()
        {
            if (Connected)
            {
                return RouteDetails();
            }
            string progId = FindAvailableProgId();
            if (String.IsNullOrEmpty(progId))
            {
                throw new GatewayException(
                    503,
                    "MX_COMPONENT_UNAVAILABLE",
                    "MX Component ActProgType is not installed for this gateway architecture."
                );
            }

            object candidate = null;
            try
            {
                Type type = Type.GetTypeFromProgID(progId, true);
                candidate = Activator.CreateInstance(type);
                dynamic control = candidate;
                control.ActCpuType = CpuFx3UC;
                control.ActUnitType = UnitSimulator2;
                control.ActTargetSimulator = TargetSimulatorForFxCpu;

                int unitType = Convert.ToInt32(control.ActUnitType, CultureInfo.InvariantCulture);
                int cpuType = Convert.ToInt32(control.ActCpuType, CultureInfo.InvariantCulture);
                int target = Convert.ToInt32(control.ActTargetSimulator, CultureInfo.InvariantCulture);
                if (unitType != UnitSimulator2 || cpuType != CpuFx3UC || target != TargetSimulatorForFxCpu)
                {
                    throw new GatewayException(
                        500,
                        "ROUTE_ATTESTATION_FAILED",
                        "MX Component did not retain the required GX Simulator2-only route."
                    );
                }

                int result = Convert.ToInt32(control.Open(), CultureInfo.InvariantCulture);
                if (result != 0)
                {
                    throw new GatewayException(
                        503,
                        "SIMULATOR_CONNECT_FAILED",
                        "MX Component could not open GX Simulator2 (" + FormatMxCode(result) + ")."
                    );
                }
                _control = control;
                _activeProgId = progId;
                candidate = null;
                return RouteDetails();
            }
            catch (GatewayException)
            {
                throw;
            }
            catch (Exception error)
            {
                throw new GatewayException(
                    503,
                    "SIMULATOR_CONNECT_FAILED",
                    "GX Simulator2 connection failed: " + error.Message
                );
            }
            finally
            {
                ReleaseComObject(candidate);
            }
        }

        public IDictionary<string, object> RouteDetails()
        {
            Dictionary<string, object> result = new Dictionary<string, object>();
            result["simulator_only"] = true;
            result["route"] = "GX Simulator2";
            result["unit_type"] = UnitSimulator2;
            result["cpu_type"] = CpuFx3UC;
            result["target_simulator"] = TargetSimulatorForFxCpu;
            result["plc_model"] = "FX3U";
            result["prog_id"] = _activeProgId;
            result["connected"] = Connected;
            return result;
        }

        public IDictionary<string, object> ReadMany(IList<object> rawAddresses)
        {
            EnsureConnected();
            if (rawAddresses == null || rawAddresses.Count == 0 || rawAddresses.Count > 256)
            {
                throw new GatewayException(400, "INVALID_ADDRESS_LIST", "Read requests require 1 to 256 addresses.");
            }
            List<string> addresses = new List<string>();
            foreach (object item in rawAddresses)
            {
                addresses.Add(ValidateAddress(Convert.ToString(item, CultureInfo.InvariantCulture), false));
            }
            Dictionary<string, object> values = new Dictionary<string, object>();
            foreach (string address in addresses)
            {
                Match match = DevicePattern.Match(address);
                string prefix = match.Groups[1].Value.ToUpperInvariant();
                string device = prefix == "C" ? "CN" + match.Groups[2].Value
                    : prefix == "T" ? "TN" + match.Groups[2].Value
                    : address;
                int data = 0;
                int result = Convert.ToInt32(_control.GetDevice(device, out data), CultureInfo.InvariantCulture);
                if (result != 0)
                {
                    throw new GatewayException(
                        502,
                        "MX_READ_FAILED",
                        "MX Component failed to read " + address + " (" + FormatMxCode(result) + ")."
                    );
                }
                values[address] = data;
            }
            return values;
        }

        public void WriteMany(IDictionary<string, object> rawValues)
        {
            EnsureConnected();
            if (rawValues == null || rawValues.Count == 0 || rawValues.Count > 256)
            {
                throw new GatewayException(400, "INVALID_DEVICE_VALUES", "Write requests require 1 to 256 values.");
            }
            List<KeyValuePair<string, int>> values = new List<KeyValuePair<string, int>>();
            foreach (KeyValuePair<string, object> item in rawValues)
            {
                string address = ValidateAddress(item.Key, true);
                int value;
                try
                {
                    value = Convert.ToInt32(item.Value, CultureInfo.InvariantCulture);
                }
                catch (Exception)
                {
                    throw new GatewayException(400, "INVALID_DEVICE_VALUE", address + " requires an integer value.");
                }
                string prefix = DevicePattern.Match(address).Groups[1].Value.ToUpperInvariant();
                if ((prefix == "X" || prefix == "M") && value != 0 && value != 1)
                {
                    throw new GatewayException(400, "INVALID_BIT_VALUE", address + " accepts only 0 or 1.");
                }
                if (prefix == "D" && (value < -32768 || value > 65535))
                {
                    throw new GatewayException(400, "INVALID_WORD_VALUE", address + " is outside the 16-bit word range.");
                }
                values.Add(new KeyValuePair<string, int>(address, value));
            }

            foreach (KeyValuePair<string, int> item in values)
            {
                int result = Convert.ToInt32(_control.SetDevice(item.Key, item.Value), CultureInfo.InvariantCulture);
                if (result != 0)
                {
                    throw new GatewayException(
                        502,
                        "MX_WRITE_FAILED",
                        "MX Component failed to write " + item.Key + " (" + FormatMxCode(result) + ")."
                    );
                }
            }
        }

        public IDictionary<string, object> ResetCpu(
            IList<object> rawDevices,
            IDictionary<string, object> rawInitialValues
        )
        {
            EnsureConnected();
            if (rawDevices == null || rawDevices.Count > 256)
            {
                throw new GatewayException(
                    400,
                    "INVALID_RESET_DEVICE_LIST",
                    "CPU reset accepts zero to 256 program-owned devices."
                );
            }
            if (rawInitialValues == null || rawInitialValues.Count > 256)
            {
                throw new GatewayException(
                    400,
                    "INVALID_INITIAL_VALUES",
                    "CPU reset accepts zero to 256 initial input values."
                );
            }

            // MX Component's official sample defines SetCpuStatus operations
            // as 0=RUN, 1=STOP, 2=PAUSE, 3=RESET.  Simulator2 does not reliably
            // clear every non-retentive device through remote RESET alone, so
            // the caller also supplies the program-owned devices to clear.
            int stopResult = Convert.ToInt32(
                _control.SetCpuStatus(1),
                CultureInfo.InvariantCulture
            );
            if (stopResult != 0)
            {
                throw new GatewayException(
                    502,
                    "MX_CPU_STOP_FAILED",
                    "MX Component could not stop the Simulator2 CPU before reset (" + FormatMxCode(stopResult) + ")."
                );
            }

            Thread.Sleep(100);
            List<string> cleared = new List<string>();
            foreach (object rawDevice in rawDevices)
            {
                string address = ValidateAddress(
                    Convert.ToString(rawDevice, CultureInfo.InvariantCulture),
                    false
                );
                Match match = DevicePattern.Match(address);
                string prefix = match.Groups[1].Value.ToUpperInvariant();
                int index = prefix == "X" || prefix == "Y"
                    ? Convert.ToInt32(match.Groups[2].Value, 8)
                    : Convert.ToInt32(match.Groups[2].Value, CultureInfo.InvariantCulture);
                if (prefix == "X" || (prefix == "M" || prefix == "D") && index >= 8000)
                {
                    throw new GatewayException(
                        403,
                        "RESET_DEVICE_NOT_ALLOWED",
                        "CPU reset may clear only program-owned M/D/T/C/S/Y devices."
                    );
                }
                string target = prefix == "C" ? "CN" + match.Groups[2].Value
                    : prefix == "T" ? "TN" + match.Groups[2].Value
                    : address;
                int clearResult = Convert.ToInt32(
                    _control.SetDevice(target, 0),
                    CultureInfo.InvariantCulture
                );
                if (clearResult != 0)
                {
                    throw new GatewayException(
                        502,
                        "MX_DEVICE_CLEAR_FAILED",
                        "MX Component could not clear " + address + " before the test (" + FormatMxCode(clearResult) + ")."
                    );
                }
                cleared.Add(address);
            }

            Dictionary<string, int> initialized = new Dictionary<string, int>();
            foreach (KeyValuePair<string, object> item in rawInitialValues)
            {
                string address = ValidateAddress(item.Key, true);
                int value;
                try
                {
                    value = Convert.ToInt32(item.Value, CultureInfo.InvariantCulture);
                }
                catch (Exception)
                {
                    throw new GatewayException(
                        400,
                        "INVALID_DEVICE_VALUE",
                        address + " requires an integer initial value."
                    );
                }
                string prefix = DevicePattern.Match(address).Groups[1].Value.ToUpperInvariant();
                if ((prefix == "X" || prefix == "M") && value != 0 && value != 1)
                {
                    throw new GatewayException(
                        400,
                        "INVALID_BIT_VALUE",
                        address + " accepts only 0 or 1."
                    );
                }
                if (prefix == "D" && (value < -32768 || value > 65535))
                {
                    throw new GatewayException(
                        400,
                        "INVALID_WORD_VALUE",
                        address + " is outside the 16-bit word range."
                    );
                }
                int initializeResult = Convert.ToInt32(
                    _control.SetDevice(address, value),
                    CultureInfo.InvariantCulture
                );
                if (initializeResult != 0)
                {
                    throw new GatewayException(
                        502,
                        "MX_INITIALIZE_FAILED",
                        "MX Component could not initialize " + address + " before RUN (" + FormatMxCode(initializeResult) + ")."
                    );
                }
                initialized[address] = value;
            }

            // Simulator2 may resume scanning as part of RESET itself.  Put
            // every test's initial inputs/state in place while the CPU is
            // definitely stopped, before RESET can execute a first scan.
            // Doing this afterwards allows a stale ON input from the previous
            // case to retrigger an ANDP/PLS instruction for one scan.
            int resetResult = Convert.ToInt32(
                _control.SetCpuStatus(3),
                CultureInfo.InvariantCulture
            );
            if (resetResult != 0)
            {
                throw new GatewayException(
                    502,
                    "MX_CPU_RESET_FAILED",
                    "MX Component could not reset the Simulator2 CPU (" + FormatMxCode(resetResult) + ")."
                );
            }

            Thread.Sleep(100);

            int runResult = Convert.ToInt32(
                _control.SetCpuStatus(0),
                CultureInfo.InvariantCulture
            );
            if (runResult != 0)
            {
                throw new GatewayException(
                    502,
                    "MX_CPU_RUN_FAILED",
                    "MX Component could not return the Simulator2 CPU to RUN (" + FormatMxCode(runResult) + ")."
                );
            }

            DateTime deadline = DateTime.UtcNow.AddSeconds(5);
            int runMonitor = 0;
            int monitorResult = -1;
            while (DateTime.UtcNow < deadline)
            {
                monitorResult = Convert.ToInt32(
                    _control.GetDevice("M8000", out runMonitor),
                    CultureInfo.InvariantCulture
                );
                if (monitorResult == 0 && runMonitor == 1)
                {
                    return new Dictionary<string, object>
                    {
                        { "reset", true },
                        { "cpu_run", true },
                        { "run_monitor", runMonitor },
                        { "cleared_devices", cleared.ToArray() },
                        { "initial_values", initialized }
                    };
                }
                Thread.Sleep(50);
            }

            throw new GatewayException(
                503,
                "CPU_RUN_TIMEOUT",
                "Simulator2 CPU did not return to RUN after reset (" + FormatMxCode(monitorResult) + ")."
            );
        }

        public void Disconnect()
        {
            object current = _control;
            _control = null;
            _activeProgId = "";
            if (current == null)
            {
                return;
            }
            try
            {
                dynamic control = current;
                control.Close();
            }
            catch (Exception)
            {
            }
            finally
            {
                ReleaseComObject(current);
            }
        }

        private static string ValidateAddress(string raw, bool writable)
        {
            string address = (raw ?? "").Trim().ToUpperInvariant();
            Match match = DevicePattern.Match(address);
            if (!match.Success)
            {
                throw new GatewayException(400, "INVALID_DEVICE_ADDRESS", "Unsupported FX3U device address: " + address);
            }
            string prefix = match.Groups[1].Value.ToUpperInvariant();
            string digits = match.Groups[2].Value;
            int index;
            if (prefix == "X" || prefix == "Y")
            {
                foreach (char character in digits)
                {
                    if (character < '0' || character > '7')
                    {
                        throw new GatewayException(400, "INVALID_DEVICE_ADDRESS", address + " is not a valid FX3U octal address.");
                    }
                }
                index = Convert.ToInt32(digits, 8);
                if (index > Convert.ToInt32("367", 8))
                {
                    throw new GatewayException(400, "INVALID_DEVICE_ADDRESS", address + " exceeds the FX3U device range.");
                }
            }
            else
            {
                if (!Int32.TryParse(digits, NumberStyles.None, CultureInfo.InvariantCulture, out index))
                {
                    throw new GatewayException(400, "INVALID_DEVICE_ADDRESS", "Invalid device index: " + address);
                }
                int maximum = prefix == "M" || prefix == "D" ? 8511
                    : prefix == "T" ? 511
                    : prefix == "C" ? 255
                    : 4095;
                if (index > maximum)
                {
                    throw new GatewayException(400, "INVALID_DEVICE_ADDRESS", address + " exceeds the FX3U device range.");
                }
            }
            if (writable)
            {
                if (prefix != "X" && prefix != "M" && prefix != "D")
                {
                    throw new GatewayException(403, "WRITE_NOT_ALLOWED", "Tests may write only X, M, or D devices.");
                }
                if ((prefix == "M" || prefix == "D") && index >= 8000)
                {
                    throw new GatewayException(403, "SPECIAL_DEVICE_WRITE_BLOCKED", "CPU-owned special devices cannot be written.");
                }
            }
            return address;
        }

        private void EnsureConnected()
        {
            if (!Connected)
            {
                throw new GatewayException(409, "NOT_CONNECTED", "GX Simulator2 is not connected.");
            }
        }

        private static string FormatMxCode(int code)
        {
            return "0x" + unchecked((uint)code).ToString("X8", CultureInfo.InvariantCulture);
        }

        private static void ReleaseComObject(object value)
        {
            if (value != null && Marshal.IsComObject(value))
            {
                try
                {
                    Marshal.FinalReleaseComObject(value);
                }
                catch (Exception)
                {
                }
            }
        }

        public void Dispose()
        {
            Disconnect();
        }
    }

    internal sealed class HttpRequestData
    {
        public string Method = "";
        public string Path = "";
        public readonly Dictionary<string, string> Headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        public string Body = "";
    }

    internal sealed class LoopbackGateway : IDisposable
    {
        private const int MaximumHeaderBytes = 16384;
        private const int MaximumBodyBytes = 65536;
        private readonly GatewayConfig _config;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private readonly MxSimulatorConnection _mx;
        private TcpListener _listener;
        private volatile bool _running;

        public LoopbackGateway(GatewayConfig config)
        {
            _config = config;
            _mx = new MxSimulatorConnection(config.ProgId);
            _json.MaxJsonLength = MaximumBodyBytes;
        }

        public void Run()
        {
            _listener = new TcpListener(IPAddress.Loopback, _config.Port);
            _listener.Start(8);
            _running = true;
            Console.WriteLine("GX Simulator2 gateway listening on 127.0.0.1:" + _config.Port.ToString(CultureInfo.InvariantCulture));
            while (_running)
            {
                try
                {
                    using (TcpClient client = _listener.AcceptTcpClient())
                    {
                        // CPU STOP/RESET/RUN verification can legitimately
                        // take slightly longer than the normal device I/O
                        // deadline.  Keep the transport alive for the whole
                        // versioned reset operation.
                        client.ReceiveTimeout = 20000;
                        client.SendTimeout = 20000;
                        Handle(client);
                    }
                }
                catch (SocketException)
                {
                    if (_running)
                    {
                        throw;
                    }
                }
                catch (ObjectDisposedException)
                {
                    if (_running)
                    {
                        throw;
                    }
                }
            }
        }

        public void Stop()
        {
            _running = false;
            if (_listener != null)
            {
                try { _listener.Stop(); } catch (Exception) { }
            }
        }

        private void Handle(TcpClient client)
        {
            NetworkStream stream = client.GetStream();
            int status = 200;
            Dictionary<string, object> response;
            try
            {
                HttpRequestData request = ReadRequest(stream);
                response = Route(request);
                response["ok"] = true;
            }
            catch (GatewayException error)
            {
                status = error.HttpStatus;
                response = Error(error.ErrorCode, error.Message);
            }
            catch (Exception error)
            {
                status = 500;
                response = Error("INTERNAL_ERROR", error.Message);
            }
            WriteResponse(stream, status, response);
        }

        private Dictionary<string, object> Route(HttpRequestData request)
        {
            if (request.Method == "GET" && request.Path == "/health")
            {
                Dictionary<string, object> health = new Dictionary<string, object>();
                health["service"] = "plc-ai-gx-simulator2-gateway";
                health["protocol_version"] = 2;
                health["gateway_version"] = "2.0";
                health["capabilities"] = new Dictionary<string, object>
                {
                    { "device_read", true },
                    { "device_write", true },
                    { "cpu_reset", true },
                    { "scan_monitor", true }
                };
                health["simulator_only"] = true;
                health["route"] = "GX Simulator2";
                health["unit_type"] = MxSimulatorConnection.SimulatorUnitType;
                health["plc_model"] = "FX3U";
                health["mx_component_available"] = !String.IsNullOrEmpty(_mx.FindAvailableProgId());
                health["connected"] = _mx.Connected;
                health["prog_id"] = _mx.ActiveProgId;
                return health;
            }

            RequireToken(request);
            if (request.Method == "POST" && request.Path == "/connect")
            {
                return new Dictionary<string, object>(_mx.Connect());
            }
            if (request.Method == "POST" && request.Path == "/disconnect")
            {
                _mx.Disconnect();
                return new Dictionary<string, object> { { "connected", false } };
            }
            if (request.Method == "POST" && request.Path == "/devices/read")
            {
                Dictionary<string, object> payload = ParseObject(request.Body);
                IList<object> addresses = payload.ContainsKey("addresses") ? payload["addresses"] as IList<object> : null;
                return new Dictionary<string, object> { { "values", _mx.ReadMany(addresses) } };
            }
            if (request.Method == "POST" && request.Path == "/devices/write")
            {
                Dictionary<string, object> payload = ParseObject(request.Body);
                IDictionary<string, object> values = payload.ContainsKey("values")
                    ? payload["values"] as IDictionary<string, object>
                    : null;
                _mx.WriteMany(values);
                return new Dictionary<string, object> { { "written", values.Count } };
            }
            if (request.Method == "POST" && request.Path == "/cpu/reset")
            {
                Dictionary<string, object> payload = ParseObject(request.Body);
                IList<object> devices = payload.ContainsKey("devices")
                    ? payload["devices"] as IList<object>
                    : new List<object>();
                IDictionary<string, object> initialValues = payload.ContainsKey("initial_values")
                    ? payload["initial_values"] as IDictionary<string, object>
                    : new Dictionary<string, object>();
                return new Dictionary<string, object>(
                    _mx.ResetCpu(devices, initialValues)
                );
            }
            if (request.Method == "POST" && request.Path == "/shutdown")
            {
                _mx.Disconnect();
                _running = false;
                return new Dictionary<string, object> { { "stopping", true } };
            }
            throw new GatewayException(404, "NOT_FOUND", "Unknown gateway endpoint.");
        }

        private void RequireToken(HttpRequestData request)
        {
            string supplied;
            if (!request.Headers.TryGetValue("X-PLC-Gateway-Token", out supplied)
                || !ConstantTimeEquals(supplied, _config.Token))
            {
                throw new GatewayException(401, "UNAUTHORIZED", "A valid gateway token is required.");
            }
        }

        private static bool ConstantTimeEquals(string left, string right)
        {
            byte[] a = Encoding.UTF8.GetBytes(left ?? "");
            byte[] b = Encoding.UTF8.GetBytes(right ?? "");
            int difference = a.Length ^ b.Length;
            int length = Math.Max(a.Length, b.Length);
            for (int index = 0; index < length; index++)
            {
                byte av = index < a.Length ? a[index] : (byte)0;
                byte bv = index < b.Length ? b[index] : (byte)0;
                difference |= av ^ bv;
            }
            return difference == 0;
        }

        private Dictionary<string, object> ParseObject(string body)
        {
            object value;
            try
            {
                value = _json.DeserializeObject(body ?? "");
            }
            catch (Exception)
            {
                throw new GatewayException(400, "INVALID_JSON", "Request body must be valid JSON.");
            }
            Dictionary<string, object> result = value as Dictionary<string, object>;
            if (result == null)
            {
                throw new GatewayException(400, "INVALID_JSON", "Request body must be a JSON object.");
            }
            return result;
        }

        private static HttpRequestData ReadRequest(NetworkStream stream)
        {
            MemoryStream headerBuffer = new MemoryStream();
            int matched = 0;
            byte[] terminator = new byte[] { 13, 10, 13, 10 };
            while (headerBuffer.Length < MaximumHeaderBytes)
            {
                int value = stream.ReadByte();
                if (value < 0)
                {
                    throw new GatewayException(400, "INVALID_HTTP", "Connection ended before the HTTP headers completed.");
                }
                headerBuffer.WriteByte((byte)value);
                if ((byte)value == terminator[matched])
                {
                    matched++;
                    if (matched == terminator.Length)
                    {
                        break;
                    }
                }
                else
                {
                    matched = (byte)value == terminator[0] ? 1 : 0;
                }
            }
            if (matched != terminator.Length)
            {
                throw new GatewayException(431, "HEADERS_TOO_LARGE", "HTTP headers are too large.");
            }
            string headerText = Encoding.ASCII.GetString(headerBuffer.ToArray());
            string[] lines = headerText.Split(new string[] { "\r\n" }, StringSplitOptions.None);
            string[] requestLine = lines[0].Split(' ');
            if (requestLine.Length < 2)
            {
                throw new GatewayException(400, "INVALID_HTTP", "Invalid HTTP request line.");
            }
            HttpRequestData request = new HttpRequestData();
            request.Method = requestLine[0].ToUpperInvariant();
            request.Path = requestLine[1].Split('?')[0];
            for (int index = 1; index < lines.Length; index++)
            {
                int separator = lines[index].IndexOf(':');
                if (separator > 0)
                {
                    request.Headers[lines[index].Substring(0, separator).Trim()] = lines[index].Substring(separator + 1).Trim();
                }
            }
            string rawLength;
            int contentLength = 0;
            if (request.Headers.TryGetValue("Content-Length", out rawLength)
                && (!Int32.TryParse(rawLength, out contentLength) || contentLength < 0))
            {
                throw new GatewayException(400, "INVALID_HTTP", "Invalid Content-Length header.");
            }
            if (contentLength > MaximumBodyBytes)
            {
                throw new GatewayException(413, "BODY_TOO_LARGE", "Request body is too large.");
            }
            byte[] body = new byte[contentLength];
            int offset = 0;
            while (offset < contentLength)
            {
                int read = stream.Read(body, offset, contentLength - offset);
                if (read <= 0)
                {
                    throw new GatewayException(400, "INVALID_HTTP", "Connection ended before the request body completed.");
                }
                offset += read;
            }
            request.Body = Encoding.UTF8.GetString(body);
            return request;
        }

        private void WriteResponse(NetworkStream stream, int status, Dictionary<string, object> payload)
        {
            byte[] body = Encoding.UTF8.GetBytes(_json.Serialize(payload));
            string reason = status == 200 ? "OK"
                : status == 400 ? "Bad Request"
                : status == 401 ? "Unauthorized"
                : status == 403 ? "Forbidden"
                : status == 404 ? "Not Found"
                : status == 409 ? "Conflict"
                : status == 413 ? "Payload Too Large"
                : status == 431 ? "Request Header Fields Too Large"
                : status == 502 ? "Bad Gateway"
                : status == 503 ? "Service Unavailable"
                : "Internal Server Error";
            string headers = "HTTP/1.1 " + status.ToString(CultureInfo.InvariantCulture) + " " + reason + "\r\n"
                + "Content-Type: application/json; charset=utf-8\r\n"
                + "Content-Length: " + body.Length.ToString(CultureInfo.InvariantCulture) + "\r\n"
                + "Cache-Control: no-store\r\n"
                + "Connection: close\r\n\r\n";
            byte[] head = Encoding.ASCII.GetBytes(headers);
            stream.Write(head, 0, head.Length);
            stream.Write(body, 0, body.Length);
            stream.Flush();
        }

        private static Dictionary<string, object> Error(string code, string message)
        {
            return new Dictionary<string, object>
            {
                { "ok", false },
                { "error_code", code },
                { "error", message }
            };
        }

        public void Dispose()
        {
            Stop();
            _mx.Dispose();
        }
    }

    internal static class Program
    {
        [STAThread]
        private static int Main()
        {
            try
            {
                GatewayConfig config = new GatewayConfig();
                using (LoopbackGateway gateway = new LoopbackGateway(config))
                {
                    Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs args)
                    {
                        args.Cancel = true;
                        gateway.Stop();
                    };
                    gateway.Run();
                }
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.Message);
                return 1;
            }
        }
    }
}
