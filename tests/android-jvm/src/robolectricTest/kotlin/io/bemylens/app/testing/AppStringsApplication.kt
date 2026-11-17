package io.bemylens.app.testing

import android.app.Application
import android.content.res.Resources
import io.bemylens.app.R
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * An Application whose resources answer the app's own `R.string` IDs with the real text
 * from app/src/main/res/values/strings.xml.
 *
 * The harness cannot run aapt2, so it generates R.string itself (see generateR in
 * build.gradle.kts). Context.getString() always goes through getResources(), so
 * production code calling getString(R.string.x, ...) gets the app's actual Arabic text.
 * Use with `@Config(application = AppStringsApplication::class)`.
 */
class AppStringsApplication : Application() {
    private var appResources: Resources? = null

    override fun getResources(): Resources {
        appResources?.let { return it }
        val base = super.getResources()
        @Suppress("DEPRECATION")
        val resources = object : Resources(base.assets, base.displayMetrics, base.configuration) {
            override fun getString(id: Int): String = AppStrings.byId[id] ?: base.getString(id)

            override fun getString(id: Int, vararg formatArgs: Any?): String = String.format(getString(id), *formatArgs)

            override fun getText(id: Int): CharSequence = getString(id)
        }
        appResources = resources
        return resources
    }
}

object AppStrings {
    private val byName: Map<String, String> by lazy {
        val file = File(System.getProperty("bemylens.stringsXml") ?: error("bemylens.stringsXml is not set"))
        val strings = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file).getElementsByTagName("string")
        (0 until strings.length).associate { index ->
            val element = strings.item(index) as org.w3c.dom.Element
            element.getAttribute("name") to unescape(element.textContent)
        }
    }

    /** R.string ID to text, matched through the generated R class's field names. */
    val byId: Map<Int, String> by lazy {
        R.string::class.java.fields.associate { field -> field.getInt(null) to byName.getValue(field.name) }
    }

    fun get(id: Int): String = byId.getValue(id)

    /** The escapes Android applies to string resources. */
    private fun unescape(raw: String): String {
        val text = raw.trim().removeSurrounding("\"")
        return Regex("""\\(.)""").replace(text) { match ->
            when (val escaped = match.groupValues[1]) {
                "n" -> "\n"
                "t" -> "\t"
                else -> escaped
            }
        }
    }
}
