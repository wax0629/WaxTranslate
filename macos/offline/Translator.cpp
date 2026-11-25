#include "ctranslate2/translator.h"
#include "sentencepiece_processor.h"
#include <algorithm>
#include <cctype>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>

// UTF-8 offsets travel with each occurrence so repeated words keep their identity.
namespace {
using Tokens = std::vector<std::string>;
using Encoded = sentencepiece::ImmutableSentencePieceText;

struct Engine {
  sentencepiece::SentencePieceProcessor tokenizer;
  ctranslate2::Translator translator;

  explicit Engine(const std::string& directory)
    : translator(directory + "/model", ctranslate2::Device::CPU, ctranslate2::ComputeType::FLOAT32,
                 {0}, false, {2}) {
    auto status = tokenizer.Load(directory + "/sentencepiece.model");
    if (!status.ok()) throw std::runtime_error(status.ToString());
  }
};

void align(const Encoded& source, const Encoded& target,
           const ctranslate2::TranslationResult& output, int begin, int end, int* lo, int* hi) {
  if (output.attention.empty() || begin < 0 || end <= begin) return;
  const auto& attention = output.attention.front();
  if (attention.empty() || attention.size() < target.pieces_size()) return;
  const int extra = int(attention.front().size()) - int(source.pieces_size());
  if (extra != 0 && extra != 2) return;
  int first = -1, last = -1;
  for (size_t i = 0; i < target.pieces_size(); ++i) {
    const auto& row = attention[i];
    if (row.size() != source.pieces_size() + extra) return;
    const auto surface = target.pieces(i).surface();
    if (std::none_of(surface.begin(), surface.end(), [](unsigned char ch) { return ch >= 128 || std::isalnum(ch); })) continue;
    auto peak = std::max_element(row.begin(), row.end()) - row.begin();
    float mass = 0;
    bool selectedPeak = false;
    for (size_t j = 0; j < source.pieces_size(); ++j) {
      auto token = source.pieces(j);
      if (int(token.begin()) >= end || int(token.end()) <= begin) continue;
      const size_t index = j + extra / 2;
      mass += row[index];
      if (size_t(peak) == index) selectedPeak = true;
    }
    if (!selectedPeak || mass < 0.40f) continue;
    if (last >= 0 && int(i) != last + 1) return;
    if (first < 0) first = int(i);
    last = int(i);
  }
  if (first < 0) return;
  const int start = target.pieces(first).begin(), finish = target.pieces(last).end();
  if (finish <= start || (start == 0 && size_t(finish) == target.text().size())) return;
  *lo = start;
  *hi = finish;
}
}

// The caller frees the returned UTF-8 string with the system allocator.
extern "C" char* wax_translate(const char* folder, const char* input, int begin, int end,
                                int* target_begin, int* target_end) noexcept {
  static std::mutex mutex;
  static std::map<std::string, std::unique_ptr<Engine>> engines;
  *target_begin = *target_end = -1;
  try {
    std::lock_guard<std::mutex> guard(mutex);
    auto& engine = engines[folder];
    if (!engine) engine = std::make_unique<Engine>(folder);
    auto source = engine->tokenizer.EncodeAsImmutableProto(input);
    Tokens tokens;
    for (const auto& token : source.pieces()) tokens.push_back(token.piece());
    if (tokens.empty()) return nullptr;
    // The model's input window is bounded. Keep every token in long sentences.
    std::vector<Tokens> batches;
    constexpr size_t window = 200;
    for (size_t i = 0; i < tokens.size(); i += window)
      batches.emplace_back(tokens.begin() + i, tokens.begin() + std::min(i + window, tokens.size()));
    ctranslate2::TranslationOptions options;
    options.beam_size = 4;
    options.max_decoding_length = 512;
    options.replace_unknowns = true;
    options.return_attention = begin >= 0 && batches.size() == 1;
    auto outputs = engine->translator.translate_batch(batches, options, 8);
    std::string text;
    for (const auto& output : outputs) {
      auto target = engine->tokenizer.DecodePiecesAsImmutableProto(output.hypotheses.at(0));
      if (options.return_attention) align(source, target, output, begin, end, target_begin, target_end);
      if (!text.empty()) text += " ";
      text += target.text();
    }
    return strdup(text.c_str());
  } catch (const std::exception&) {
    return nullptr;
  }
}
