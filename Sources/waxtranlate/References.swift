import Foundation

struct WordReference: Identifiable, Equatable {
    let id: String
    let description: String
    var url: URL { URL(string: "https://www.wikidata.org/wiki/" + id)! }
}

enum WordReferences {
    static func request(for word: String) -> URLRequest? {
        guard word.count <= 96,
              word.range(of: #"^[\w.+#’'\-]+$"#, options: .regularExpression) != nil else { return nil }
        var url = URLComponents(string: "https://www.wikidata.org/w/api.php")!
        url.queryItems = ["action": "wbsearchentities", "search": word, "language": "en", "uselang": "zh-hans",
                          "type": "item", "limit": "8", "format": "json"].map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: url.url!, timeoutInterval: 6)
        request.setValue("WaxTranslate/0.3 (https://github.com/wax0629/WaxTranslate)", forHTTPHeaderField: "User-Agent")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    static func search(_ word: String) async throws -> [WordReference] {
        guard let request = request(for: word) else { return [] }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200, data.count <= 256 * 1024 else {
            throw URLError(.badServerResponse)
        }
        return try parse(data, word: word)
    }

    static func parse(_ data: Data, word: String) throws -> [WordReference] {
        struct Response: Decodable {
            struct Item: Decodable {
                struct Match: Decodable { let text: String? }
                let id: String
                let description: String?
                let match: Match?
            }
            let search: [Item]
        }
        let response = try JSONDecoder().decode(Response.self, from: data)
        var result: [WordReference] = []
        for item in response.search {
            guard item.match?.text?.caseInsensitiveCompare(word) == .orderedSame,
                  item.id.range(of: #"^Q[1-9][0-9]*$"#, options: .regularExpression) != nil,
                  let description = item.description?.trimmingCharacters(in: .whitespacesAndNewlines), !description.isEmpty,
                  !result.contains(where: { $0.description == description }) else { continue }
            result.append(WordReference(id: item.id, description: String(description.prefix(350))))
            if result.count == 3 { break }
        }
        return result
    }
}
