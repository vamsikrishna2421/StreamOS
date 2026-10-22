import AVKit
import SwiftUI

/// Channel list + AVPlayer. Touch-first; the same hub backs the TV client, so
/// watching the same channel here shares the upstream session automatically.
struct ContentView: View {
    @State private var sources: [Source] = []
    @State private var error: String?
    @State private var player = AVPlayer()
    @State private var nowPlaying: String?

    private let hub = HubClient()
    private let deviceId = DeviceID.current

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                VideoPlayer(player: player)
                    .frame(height: 230)
                    .background(Color.black)
                    .overlay(alignment: .topLeading) {
                        if let np = nowPlaying {
                            Text(np).font(.caption).padding(6)
                                .background(.black.opacity(0.5)).foregroundStyle(.white)
                                .padding(8)
                        }
                    }
                List(sources) { s in
                    Button { play(s) } label: {
                        HStack {
                            Image(systemName: s.kind == "live" ? "dot.radiowaves.left.and.right" : "film")
                            VStack(alignment: .leading) {
                                Text(s.name).font(.body)
                                Text(s.kind.uppercased()).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("StreamOS")
            .task { await load() }
            .alert("Error", isPresented: .constant(error != nil)) {
                Button("OK") { error = nil }
            } message: { Text(error ?? "") }
        }
    }

    private func load() async {
        do { sources = try await hub.listSources() }
        catch { self.error = "Hub unreachable: \(error.localizedDescription)" }
    }

    private func play(_ s: Source) {
        Task {
            do {
                let res = try await hub.play(deviceId: deviceId, sourceId: s.id)
                guard res.ok, let u = res.play_url else {
                    self.error = "Can't play: \(res.reason ?? "error")"; return
                }
                player.replaceCurrentItem(with: AVPlayerItem(url: hub.absolute(u)))
                player.play()
                nowPlaying = "\(s.name) · \(res.mode)"
            } catch { self.error = error.localizedDescription }
        }
    }
}

enum DeviceID {
    static let current: String = {
        let key = "streamos.device_id"
        if let v = UserDefaults.standard.string(forKey: key) { return v }
        let v = String(UUID().uuidString.prefix(12))
        UserDefaults.standard.set(v, forKey: key)
        return v
    }()
}
