function doGet(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    
    // 1. Tarik Data Toko
    var sheetToko = ss.getSheetByName("list toko"); 
    var dataToko = sheetToko.getDataRange().getValues();
    var headersToko = dataToko[0];
    var stores = [];
    
    for (var i = 1; i < dataToko.length; i++) {
      var row = dataToko[i];
      var storeObj = {};
      for (var j = 0; j < headersToko.length; j++) {
        storeObj[headersToko[j]] = row[j]; 
      }
      stores.push(storeObj);
    }
    
    // 2. Tarik Base Data Produk (Biar tetep dapet barcode walau ga promo)
    var sheetAllProduk = ss.getSheetByName("all produk");
    var dataAllProduk = sheetAllProduk.getDataRange().getValues();
    var headersAllProduk = dataAllProduk[0];
    var products = {};
    
    for (var i = 1; i < dataAllProduk.length; i++) {
      var row = dataAllProduk[i];
      var prodName = "";
      var barcode = "";
      
      for (var j = 0; j < headersAllProduk.length; j++) {
        var key = headersAllProduk[j].toString().trim();
        if (key === "desc") prodName = row[j];
        if (key === "barcode") barcode = row[j];
      }
      
      if (prodName !== "") {
        products[prodName] = {
          "barcode": barcode,
          "jenis_promo": "",
          "mulai_promo": "",
          "akhir_promo": ""
        };
      }
    }
    
    // 3. Tarik Data Promo buat ditiban ke data Produk
    var sheetPromo = ss.getSheetByName("promo");
    if (sheetPromo) {
      var dataPromo = sheetPromo.getDataRange().getValues();
      var headersPromo = dataPromo[0];
      
      for (var i = 1; i < dataPromo.length; i++) {
        var row = dataPromo[i];
        var prodName = "";
        var promoData = {};
        
        for (var j = 0; j < headersPromo.length; j++) {
          var key = headersPromo[j].toString().trim();
          var value = row[j];
          
          if (key === "desc") {
            prodName = value;
          } else if (key === "jenis promo") {
            promoData["jenis_promo"] = value;
          } else if (key === "mulai promo" || key === "akhir promo") {
            // Biar format tanggal Google Sheet ga error pas jadi JSON
            var formattedDate = (value instanceof Date) ? Utilities.formatDate(value, Session.getScriptTimeZone(), "dd/MM/yyyy") : value;
            if (key === "mulai promo") promoData["mulai_promo"] = formattedDate;
            if (key === "akhir promo") promoData["akhir_promo"] = formattedDate;
          }
        }
        
        // Update data produk dengan info promo
        if (prodName !== "" && products[prodName]) {
          products[prodName]["jenis_promo"] = promoData["jenis_promo"] || "";
          products[prodName]["mulai_promo"] = promoData["mulai_promo"] || "";
          products[prodName]["akhir_promo"] = promoData["akhir_promo"] || "";
        }
      }
    }
    
    // 4. Gabungin Semua
    var result = {
      "stores": stores,
      "products": products
    };
    
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"error": error.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}