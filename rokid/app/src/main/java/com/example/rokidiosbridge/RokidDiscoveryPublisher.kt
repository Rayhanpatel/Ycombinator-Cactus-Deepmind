package com.example.rokidiosbridge

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo

class RokidDiscoveryPublisher(
    context: Context,
    private val serviceName: String,
    private val port: Int,
    private val listener: Listener
) {

    interface Listener {
        fun onAdvertised(serviceName: String)
        fun onError(message: String, code: Int? = null)
    }

    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private var registrationListener: NsdManager.RegistrationListener? = null

    fun start() {
        if (registrationListener != null) return
        val serviceInfo = NsdServiceInfo().apply {
            serviceType = BridgeConfig.SERVICE_TYPE
            serviceName = this@RokidDiscoveryPublisher.serviceName
            this.port = this@RokidDiscoveryPublisher.port
        }

        val listenerImpl = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(nsdServiceInfo: NsdServiceInfo) {
                listener.onAdvertised(nsdServiceInfo.serviceName)
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                listener.onError("Discovery registration failed", errorCode)
            }

            override fun onServiceUnregistered(nsdServiceInfo: NsdServiceInfo) = Unit

            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                listener.onError("Discovery unregistration failed", errorCode)
            }
        }

        registrationListener = listenerImpl
        nsdManager.registerService(serviceInfo, NsdManager.PROTOCOL_DNS_SD, listenerImpl)
    }

    fun stop() {
        val activeListener = registrationListener ?: return
        runCatching { nsdManager.unregisterService(activeListener) }
        registrationListener = null
    }
}
