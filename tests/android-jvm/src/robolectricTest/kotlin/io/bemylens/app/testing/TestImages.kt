package io.bemylens.app.testing

import java.awt.Color
import java.awt.image.BufferedImage
import java.io.ByteArrayInputStream
import java.io.File
import javax.imageio.ImageIO

/** Real image files written and read with the JVM's own codecs, independent of Android. */
object TestImages {
    fun writePng(file: File, width: Int, height: Int): File {
        val image = BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)
        val graphics = image.createGraphics()
        graphics.color = Color(200, 30, 30)
        graphics.fillRect(0, 0, width, height)
        graphics.color = Color.WHITE
        graphics.fillRect(width / 4, height / 4, width / 2, height / 2)
        graphics.dispose()
        file.parentFile?.mkdirs()
        check(ImageIO.write(image, "png", file)) { "no PNG writer available" }
        return file
    }

    data class Decoded(val format: String, val width: Int, val height: Int)

    fun decode(bytes: ByteArray): Decoded {
        val format = when {
            bytes.size > 2 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xD8.toByte() -> "jpeg"
            bytes.size > 8 && bytes[0] == 0x89.toByte() && bytes[1] == 'P'.code.toByte() -> "png"
            else -> "unknown"
        }
        val image = ImageIO.read(ByteArrayInputStream(bytes)) ?: throw AssertionError("not a decodable image ($format)")
        return Decoded(format, image.width, image.height)
    }
}
