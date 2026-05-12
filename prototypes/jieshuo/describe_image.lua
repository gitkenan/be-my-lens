-- Minimal Be My Lens launch prototype for a future Jieshuo .ppk extension.
-- This is not a polished extension. It is a device-testing script.

require "import"
import "android.content.Intent"
import "android.content.ComponentName"
import "android.graphics.Bitmap"
import "java.io.File"
import "java.io.FileOutputStream"

local PACKAGE_NAME = "io.bemylens.app"
local ACTIVITY_NAME = "io.bemylens.app.JieshuoEntryActivity"
local ACTION_DESCRIBE_IMAGE = "io.bemylens.app.action.DESCRIBE_IMAGE"
local EXTRA_IMAGE_URI = "io.bemylens.app.extra.IMAGE_URI"

local function launchBeMyLens(imageUri, mode, prompt, autoSpeak)
  local intent = Intent()
    .setAction(ACTION_DESCRIBE_IMAGE)
    .setComponent(ComponentName(PACKAGE_NAME, ACTIVITY_NAME))
    .setPackage(PACKAGE_NAME)
    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    .putExtra("mode", mode or "describe_screen")
    .putExtra("autoSpeak", autoSpeak ~= false)

  if prompt ~= nil and prompt ~= "" then
    intent.putExtra("prompt", prompt)
  end

  if imageUri ~= nil then
    intent.setDataAndType(imageUri, "image/png")
    intent.putExtra(Intent.EXTRA_STREAM, imageUri)
    intent.putExtra(EXTRA_IMAGE_URI, imageUri)
  end

  this.startActivity(intent)
end

local function launchNoImageSmokeTest()
  launchBeMyLens(nil, "describe_screen", nil, true)
end

local function captureAndDescribe(mode)
  if this.getScreenShot == nil then
    launchNoImageSmokeTest()
    return true
  end

  this.getScreenShot(node, {
    onScreenCaptureDone = function(bitmap)
      local file = File("/sdcard/", "be_my_lens_jieshuo.png")
      local output = FileOutputStream(file)
      bitmap.compress(Bitmap.CompressFormat.PNG, 90, output)
      output.close()

      local uri = this.getUriForFile(file)
      launchBeMyLens(uri, mode or "describe_screen", nil, true)
    end
  })

  return true
end

-- For the first device test, use describe_screen.
-- Change to "focused_item" when validating focused-item behavior.
captureAndDescribe("describe_screen")

