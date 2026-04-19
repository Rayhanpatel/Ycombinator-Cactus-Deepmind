package com.example.rokidiosbridge

import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

class BridgeSignalingServer(
    port: Int,
    private val handler: suspend (String) -> String
) : NanoHTTPD(port) {

    override fun serve(session: IHTTPSession): Response {
        return try {
            when {
                session.method == Method.GET && session.uri == "/health" -> {
                    newFixedLengthResponse(
                        Response.Status.OK,
                        "application/json",
                        """{"status":"ok"}"""
                    )
                }

                session.method == Method.POST && session.uri == "/session" -> {
                    val files = HashMap<String, String>()
                    session.parseBody(files)
                    val body = files["postData"]?.trim().orEmpty()
                    val offerSdp = parseOfferSdp(body)
                    if (offerSdp.isBlank()) {
                        newFixedLengthResponse(
                            Response.Status.BAD_REQUEST,
                            "application/json",
                            JSONObject()
                                .put("error", "Missing offer SDP")
                                .toString()
                        )
                    } else {
                        val answerSdp = runBlocking { handler(offerSdp) }
                        newFixedLengthResponse(
                            Response.Status.OK,
                            "application/json",
                            JSONObject()
                                .put("type", "answer")
                                .put("sdp", answerSdp)
                                .toString()
                        )
                    }
                }

                else -> newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "Not found")
            }
        } catch (t: Throwable) {
            newFixedLengthResponse(
                Response.Status.INTERNAL_ERROR,
                "application/json",
                JSONObject()
                    .put("error", t.message ?: "Session failed")
                    .toString()
            )
        }
    }

    private fun parseOfferSdp(body: String): String {
        if (body.isBlank()) return ""
        if (body.startsWith("{")) {
            val json = JSONObject(body)
            return sanitizeOfferSdp(normalizeSdp(json.optString("sdp", "")))
        }
        return sanitizeOfferSdp(normalizeSdp(body))
    }

    private fun normalizeSdp(raw: String): String {
        val unified = raw.replace("\r\n", "\n").replace('\r', '\n').trim()
        if (unified.isBlank()) return ""
        return unified.lines().joinToString(separator = "\r\n") + "\r\n"
    }

    private fun sanitizeOfferSdp(raw: String): String {
        val sanitized = raw
            .lineSequence()
            .filterNot { it.trim() == "a=extmap-allow-mixed" }
            .joinToString(separator = "\r\n")
        if (sanitized.isBlank()) return ""
        return sanitized + "\r\n"
    }
}
