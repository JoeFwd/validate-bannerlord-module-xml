<?xml version="1.0" encoding="UTF-8"?>
<!--
  expanded-api.xslt

  Version-agnostic XSLT patch that extends Bannerlord character/equipment XSD
  schemas to allow the expanded API attributes used by mods.

  Applied attributes (all optional xs:string):
    EquipmentRoster : siege, battle, pool
    EquipmentSet    : siege, battle, pool

  These attributes are present in the Bannerlord runtime but omitted from the
  shipped XSD files.  This transform is applied at validation time via the
  XsltPatchedXsdResolver; no hand-edited copies of any versioned XSD are needed.

  Strategy:
  1. Identity template copies every node unchanged.
  2. Targeted templates match xs:complexType that is the direct child of an
     xs:element named "EquipmentRoster" or "EquipmentSet", then append the three
     extra attribute declarations after all existing content.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <!-- Identity transform: reproduce everything unchanged by default -->
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- EquipmentRoster: inject siege / battle / pool -->
  <xsl:template match="xs:element[@name='EquipmentRoster']/xs:complexType">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <xs:attribute name="siege"  type="xs:string" use="optional"/>
      <xs:attribute name="battle" type="xs:string" use="optional"/>
      <xs:attribute name="pool"   type="xs:string" use="optional"/>
    </xsl:copy>
  </xsl:template>

  <!-- EquipmentSet: inject siege / battle / pool -->
  <xsl:template match="xs:element[@name='EquipmentSet']/xs:complexType">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <xs:attribute name="siege"  type="xs:string" use="optional"/>
      <xs:attribute name="battle" type="xs:string" use="optional"/>
      <xs:attribute name="pool"   type="xs:string" use="optional"/>
    </xsl:copy>
  </xsl:template>

</xsl:stylesheet>
