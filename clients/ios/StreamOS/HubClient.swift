import Foundation

/// Thin async client for the StreamOS hub. The hub performs stream sharing;
/// this client only lists sources, asks to play, and reports heartbeats.
struct Source: Identifiable, Decodable {
    let id: String
    let name: String
    let kind: String
}

struct PlayResult: Decodable {
    let ok: Bool
    let mode: String
    let play_url: String?
    let reason: String?
}

final class HubClient {
    /// Simulator reaches a host-run hub at localhost; use the LAN IP on device.
    let baseURL: String

    init(baseURL: String = "http://localhost:8099") {
        self.baseURL = baseURL
    }

    func listSources() async throws -> [Source] {
        let url = URL(string: "\(baseURL)/api/sources?enabled_only=true")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([Source].self, from: data)
    }

    func play(deviceId: String, sourceId: String) async throws -> PlayResult {
        var comps = URLComponents(string: "\(baseURL)/api/play")!
        comps.queryItems = [
            .init(name: "device_id", value: deviceId),
            .init(name: "source_id", value: sourceId),
        ]
        var req = URLRequest(url: comps.url!)
        req.httpMethod = "POST"
        let (data, _) = try await URLSession.shared.data(for: req)
        return try JSONDecoder().decode(PlayResult.self, from: data)
    }

    func heartbeat(sessionId: String, positionS: Double) async {
        var comps = URLComponents(string: "\(baseURL)/api/sessions/\(sessionId)/heartbeat")!
        comps.queryItems = [.init(name: "position_s", value: String(positionS))]
        var req = URLRequest(url: comps.url!)
        req.httpMethod = "POST"
        _ = try? await URLSession.shared.data(for: req)
    }

    func absolute(_ playURL: String) -> URL {
        playURL.hasPrefix("http") ? URL(string: playURL)!
                                  : URL(string: baseURL + playURL)!
    }
}
