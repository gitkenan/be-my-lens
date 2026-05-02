package io.bemylens.app.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.io.ByteArrayOutputStream
import kotlin.math.roundToInt

fun readCompressedJpeg(
    context: Context,
    imageUri: Uri,
    maxDimension: Int = 1600,
    jpegQuality: Int = 85,
): ByteArray {
    val bitmap = decodeBitmap(context, imageUri)
    val scaledBitmap = scaleBitmap(bitmap, maxDimension)
    val output = ByteArrayOutputStream()
    scaledBitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, output)
    return output.toByteArray()
}

private fun decodeBitmap(context: Context, imageUri: Uri): Bitmap {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        val source = ImageDecoder.createSource(context.contentResolver, imageUri)
        ImageDecoder.decodeBitmap(source) { decoder, _, _ ->
            decoder.isMutableRequired = false
        }
    } else {
        @Suppress("DEPRECATION")
        MediaStore.Images.Media.getBitmap(context.contentResolver, imageUri)
    }
}

private fun scaleBitmap(bitmap: Bitmap, maxDimension: Int): Bitmap {
    val width = bitmap.width
    val height = bitmap.height
    val largestSide = maxOf(width, height)
    if (largestSide <= maxDimension) return bitmap

    val scale = maxDimension.toFloat() / largestSide.toFloat()
    val scaledWidth = (width * scale).roundToInt()
    val scaledHeight = (height * scale).roundToInt()

    return Bitmap.createScaledBitmap(bitmap, scaledWidth, scaledHeight, true)
}
