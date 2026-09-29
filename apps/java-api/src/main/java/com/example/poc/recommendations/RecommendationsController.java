package com.example.poc.recommendations;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class RecommendationsController {
  private static final Logger log = LoggerFactory.getLogger(RecommendationsController.class);
  private static final Set<String> ALLOWED_SCENARIOS =
      Set.of("normal", "slow-db", "retry-success", "retry-exhaust", "stream");

  private final JdbcTemplate jdbc;
  private final RestClient analysisClient;

  public RecommendationsController(
      JdbcTemplate jdbc, @Value("${poc.analysis.base-url}") String analysisBaseUrl) {
    this.jdbc = jdbc;
    this.analysisClient = RestClient.builder().baseUrl(analysisBaseUrl).build();
  }

  @GetMapping("/healthz")
  public Map<String, String> liveness() {
    return Map.of("status", "ok");
  }

  @GetMapping("/readyz")
  public Map<String, String> readiness() {
    jdbc.queryForObject("SELECT 1", Integer.class);
    return Map.of("status", "ready");
  }

  @PostMapping(path = "/api/recommendations", consumes = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<RecommendationResponse> recommend(@RequestBody RecommendationRequest req) {
    validate(req);

    CatalogItem item =
        jdbc.query(
            "SELECT item_id, name, category FROM catalog_items WHERE item_id = ?",
            rs -> {
              if (!rs.next()) {
                return null;
              }
              return new CatalogItem(
                  rs.getString("item_id"), rs.getString("name"), rs.getString("category"));
            },
            req.itemId());

    if (item == null) {
      throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown item_id");
    }

    AnalysisRequest analysisRequest =
        new AnalysisRequest(req.requestId(), req.itemId(), item.name(), item.category(), req.scenario());

    try {
      AnalysisResponse analysis =
          analysisClient
              .post()
              .uri("/analyze")
              .contentType(MediaType.APPLICATION_JSON)
              .body(analysisRequest)
              .retrieve()
              .body(AnalysisResponse.class);

      if (analysis == null) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "empty analysis response");
      }

      log.info(
          "recommendation complete request_id={} item_id={} scenario={}",
          req.requestId(),
          req.itemId(),
          req.scenario());

      return ResponseEntity.ok(
          new RecommendationResponse(
              req.requestId(), analysis.result(), analysis.model(), analysis.status()));
    } catch (RestClientException ex) {
      log.warn(
          "analysis dependency failure request_id={}: {}", req.requestId(), ex.getMessage());
      throw new ResponseStatusException(
          HttpStatus.BAD_GATEWAY, "analysis dependency unavailable", ex);
    }
  }

  private static void validate(RecommendationRequest req) {
    if (req.requestId() == null || req.requestId().isBlank()) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "request_id required");
    }
    if (req.itemId() == null || req.itemId().isBlank()) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "item_id required");
    }
    String scenario = req.scenario() == null || req.scenario().isBlank() ? "normal" : req.scenario();
    if (!ALLOWED_SCENARIOS.contains(scenario)) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "scenario not allowlisted");
    }
  }

  public record RecommendationRequest(
      @JsonProperty("request_id") String requestId,
      @JsonProperty("item_id") String itemId,
      String scenario) {
    public RecommendationRequest {
      if (scenario == null || scenario.isBlank()) {
        scenario = "normal";
      }
    }
  }

  public record RecommendationResponse(
      @JsonProperty("request_id") String requestId,
      String result,
      String model,
      String status) {}

  public record AnalysisRequest(
      @JsonProperty("request_id") String requestId,
      @JsonProperty("item_id") String itemId,
      String name,
      String category,
      String scenario) {}

  public record AnalysisResponse(String result, String model, String status) {}

  private record CatalogItem(String itemId, String name, String category) {}
}
