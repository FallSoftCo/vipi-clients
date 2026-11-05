package co.fallsoft.vipi.core

/** One actual message/direction/configuration request, never just matching text. */
data class ImmersionPresentationRequest(val messageId: String, val text: String,
    val source: String, val target: String, val inputLanguage: String?, val configuration: Any)

/** Immutable production UI state. Visible and paused values are request-bound. */
data class ImmersionPresentationState(val request: ImmersionPresentationRequest,
    val visible: ImmersionPresentation? = null, val waiting: ImmersionPresentation? = null,
    val hasWaiting: Boolean = false) {
    fun bind(current: ImmersionPresentationRequest, cached: ImmersionPresentation? = null): ImmersionPresentationState =
        if (current == request) this else ImmersionPresentationState(current, cached)
    fun accept(current: ImmersionPresentationRequest, value: ImmersionPresentation?, paused: Boolean): ImmersionPresentationState {
        if (current != request) return this
        return if (paused) copy(waiting = value, hasWaiting = true)
        else copy(visible = value, waiting = null, hasWaiting = false)
    }
    fun resume(current: ImmersionPresentationRequest): ImmersionPresentationState =
        if (current == request && hasWaiting) copy(visible = waiting, waiting = null, hasWaiting = false) else this
}

/** Existing bounded per-conversation map: EVERY insertion enforces the limit. */
class BoundedImmersionCache<T>(private val maximum: Int = 128) {
    init { require(maximum > 0) }
    private val values = linkedMapOf<String, T>()
    val size: Int get() = values.size
    operator fun get(key: String): T? = values[key]
    operator fun set(key: String, value: T) {
        values[key] = value
        while (values.size > maximum) values.remove(values.keys.first())
    }
    fun clear() = values.clear()
}
