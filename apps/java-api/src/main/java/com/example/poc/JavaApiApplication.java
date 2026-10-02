package com.example.poc;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.JdkClientHttpRequestFactory;

@SpringBootApplication
public class JavaApiApplication {
  public static void main(String[] args) {
    SpringApplication.run(JavaApiApplication.class, args);
  }

  /** FastAPI/uvicorn rejects h2c upgrade probes from the JDK HttpClient default. */
  @Bean
  RestClientCustomizer http11Only() {
    HttpClient httpClient =
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(3))
            .build();
    JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
    factory.setReadTimeout(Duration.ofSeconds(40));
    return builder -> builder.requestFactory(factory);
  }
}
