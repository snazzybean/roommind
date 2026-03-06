(function(){"use strict";/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var Ot;const Be=globalThis,Je=Be.ShadowRoot&&(Be.ShadyCSS===void 0||Be.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Xe=Symbol(),ct=new WeakMap;let dt=class{constructor(t,i,s){if(this._$cssResult$=!0,s!==Xe)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=i}get styleSheet(){let t=this.o;const i=this.t;if(Je&&t===void 0){const s=i!==void 0&&i.length===1;s&&(t=ct.get(i)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&ct.set(i,t))}return t}toString(){return this.cssText}};const jt=e=>new dt(typeof e=="string"?e:e+"",void 0,Xe),D=(e,...t)=>{const i=e.length===1?e[0]:t.reduce((s,o,n)=>s+(a=>{if(a._$cssResult$===!0)return a.cssText;if(typeof a=="number")return a;throw Error("Value passed to 'css' function must be a 'css' function result: "+a+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+e[n+1],e[0]);return new dt(i,e,Xe)},Ut=(e,t)=>{if(Je)e.adoptedStyleSheets=t.map(i=>i instanceof CSSStyleSheet?i:i.styleSheet);else for(const i of t){const s=document.createElement("style"),o=Be.litNonce;o!==void 0&&s.setAttribute("nonce",o),s.textContent=i.cssText,e.appendChild(s)}},ht=Je?e=>e:e=>e instanceof CSSStyleSheet?(t=>{let i="";for(const s of t.cssRules)i+=s.cssText;return jt(i)})(e):e;/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const{is:Ft,defineProperty:Bt,getOwnPropertyDescriptor:Vt,getOwnPropertyNames:Kt,getOwnPropertySymbols:Zt,getPrototypeOf:Gt}=Object,ve=globalThis,pt=ve.trustedTypes,qt=pt?pt.emptyScript:"",et=ve.reactiveElementPolyfillSupport,De=(e,t)=>e,Ve={toAttribute(e,t){switch(t){case Boolean:e=e?qt:null;break;case Object:case Array:e=e==null?e:JSON.stringify(e)}return e},fromAttribute(e,t){let i=e;switch(t){case Boolean:i=e!==null;break;case Number:i=e===null?null:Number(e);break;case Object:case Array:try{i=JSON.parse(e)}catch{i=null}}return i}},tt=(e,t)=>!Ft(e,t),ut={attribute:!0,type:String,converter:Ve,reflect:!1,useDefault:!1,hasChanged:tt};Symbol.metadata??(Symbol.metadata=Symbol("metadata")),ve.litPropertyMetadata??(ve.litPropertyMetadata=new WeakMap);let Me=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??(this.l=[])).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,i=ut){if(i.state&&(i.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((i=Object.create(i)).wrapped=!0),this.elementProperties.set(t,i),!i.noAccessor){const s=Symbol(),o=this.getPropertyDescriptor(t,s,i);o!==void 0&&Bt(this.prototype,t,o)}}static getPropertyDescriptor(t,i,s){const{get:o,set:n}=Vt(this.prototype,t)??{get(){return this[i]},set(a){this[i]=a}};return{get:o,set(a){const d=o==null?void 0:o.call(this);n==null||n.call(this,a),this.requestUpdate(t,d,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??ut}static _$Ei(){if(this.hasOwnProperty(De("elementProperties")))return;const t=Gt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(De("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(De("properties"))){const i=this.properties,s=[...Kt(i),...Zt(i)];for(const o of s)this.createProperty(o,i[o])}const t=this[Symbol.metadata];if(t!==null){const i=litPropertyMetadata.get(t);if(i!==void 0)for(const[s,o]of i)this.elementProperties.set(s,o)}this._$Eh=new Map;for(const[i,s]of this.elementProperties){const o=this._$Eu(i,s);o!==void 0&&this._$Eh.set(o,i)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const i=[];if(Array.isArray(t)){const s=new Set(t.flat(1/0).reverse());for(const o of s)i.unshift(ht(o))}else t!==void 0&&i.push(ht(t));return i}static _$Eu(t,i){const s=i.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){var t;this._$ES=new Promise(i=>this.enableUpdating=i),this._$AL=new Map,this._$E_(),this.requestUpdate(),(t=this.constructor.l)==null||t.forEach(i=>i(this))}addController(t){var i;(this._$EO??(this._$EO=new Set)).add(t),this.renderRoot!==void 0&&this.isConnected&&((i=t.hostConnected)==null||i.call(t))}removeController(t){var i;(i=this._$EO)==null||i.delete(t)}_$E_(){const t=new Map,i=this.constructor.elementProperties;for(const s of i.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ut(t,this.constructor.elementStyles),t}connectedCallback(){var t;this.renderRoot??(this.renderRoot=this.createRenderRoot()),this.enableUpdating(!0),(t=this._$EO)==null||t.forEach(i=>{var s;return(s=i.hostConnected)==null?void 0:s.call(i)})}enableUpdating(t){}disconnectedCallback(){var t;(t=this._$EO)==null||t.forEach(i=>{var s;return(s=i.hostDisconnected)==null?void 0:s.call(i)})}attributeChangedCallback(t,i,s){this._$AK(t,s)}_$ET(t,i){var n;const s=this.constructor.elementProperties.get(t),o=this.constructor._$Eu(t,s);if(o!==void 0&&s.reflect===!0){const a=(((n=s.converter)==null?void 0:n.toAttribute)!==void 0?s.converter:Ve).toAttribute(i,s.type);this._$Em=t,a==null?this.removeAttribute(o):this.setAttribute(o,a),this._$Em=null}}_$AK(t,i){var n,a;const s=this.constructor,o=s._$Eh.get(t);if(o!==void 0&&this._$Em!==o){const d=s.getPropertyOptions(o),c=typeof d.converter=="function"?{fromAttribute:d.converter}:((n=d.converter)==null?void 0:n.fromAttribute)!==void 0?d.converter:Ve;this._$Em=o;const u=c.fromAttribute(i,d.type);this[o]=u??((a=this._$Ej)==null?void 0:a.get(o))??u,this._$Em=null}}requestUpdate(t,i,s,o=!1,n){var a;if(t!==void 0){const d=this.constructor;if(o===!1&&(n=this[t]),s??(s=d.getPropertyOptions(t)),!((s.hasChanged??tt)(n,i)||s.useDefault&&s.reflect&&n===((a=this._$Ej)==null?void 0:a.get(t))&&!this.hasAttribute(d._$Eu(t,s))))return;this.C(t,i,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,i,{useDefault:s,reflect:o,wrapped:n},a){s&&!(this._$Ej??(this._$Ej=new Map)).has(t)&&(this._$Ej.set(t,a??i??this[t]),n!==!0||a!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(i=void 0),this._$AL.set(t,i)),o===!0&&this._$Em!==t&&(this._$Eq??(this._$Eq=new Set)).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(i){Promise.reject(i)}const t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){var s;if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??(this.renderRoot=this.createRenderRoot()),this._$Ep){for(const[n,a]of this._$Ep)this[n]=a;this._$Ep=void 0}const o=this.constructor.elementProperties;if(o.size>0)for(const[n,a]of o){const{wrapped:d}=a,c=this[n];d!==!0||this._$AL.has(n)||c===void 0||this.C(n,void 0,a,c)}}let t=!1;const i=this._$AL;try{t=this.shouldUpdate(i),t?(this.willUpdate(i),(s=this._$EO)==null||s.forEach(o=>{var n;return(n=o.hostUpdate)==null?void 0:n.call(o)}),this.update(i)):this._$EM()}catch(o){throw t=!1,this._$EM(),o}t&&this._$AE(i)}willUpdate(t){}_$AE(t){var i;(i=this._$EO)==null||i.forEach(s=>{var o;return(o=s.hostUpdated)==null?void 0:o.call(s)}),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&(this._$Eq=this._$Eq.forEach(i=>this._$ET(i,this[i]))),this._$EM()}updated(t){}firstUpdated(t){}};Me.elementStyles=[],Me.shadowRootOptions={mode:"open"},Me[De("elementProperties")]=new Map,Me[De("finalized")]=new Map,et==null||et({ReactiveElement:Me}),(ve.reactiveElementVersions??(ve.reactiveElementVersions=[])).push("2.1.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const Re=globalThis,mt=e=>e,Ke=Re.trustedTypes,gt=Ke?Ke.createPolicy("lit-html",{createHTML:e=>e}):void 0,_t="$lit$",fe=`lit$${Math.random().toFixed(9).slice(2)}$`,vt="?"+fe,Qt=`<${vt}>`,xe=document,He=()=>xe.createComment(""),Oe=e=>e===null||typeof e!="object"&&typeof e!="function",it=Array.isArray,Yt=e=>it(e)||typeof(e==null?void 0:e[Symbol.iterator])=="function",st=`[ 	
\f\r]`,Le=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,ft=/-->/g,yt=/>/g,we=RegExp(`>|${st}(?:([^\\s"'>=/]+)(${st}*=${st}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),bt=/'/g,xt=/"/g,wt=/^(?:script|style|textarea|title)$/i,Jt=e=>(t,...i)=>({_$litType$:e,strings:t,values:i}),l=Jt(1),$e=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),$t=new WeakMap,Se=xe.createTreeWalker(xe,129);function St(e,t){if(!it(e)||!e.hasOwnProperty("raw"))throw Error("invalid template strings array");return gt!==void 0?gt.createHTML(t):t}const Xt=(e,t)=>{const i=e.length-1,s=[];let o,n=t===2?"<svg>":t===3?"<math>":"",a=Le;for(let d=0;d<i;d++){const c=e[d];let u,_,g=-1,y=0;for(;y<c.length&&(a.lastIndex=y,_=a.exec(c),_!==null);)y=a.lastIndex,a===Le?_[1]==="!--"?a=ft:_[1]!==void 0?a=yt:_[2]!==void 0?(wt.test(_[2])&&(o=RegExp("</"+_[2],"g")),a=we):_[3]!==void 0&&(a=we):a===we?_[0]===">"?(a=o??Le,g=-1):_[1]===void 0?g=-2:(g=a.lastIndex-_[2].length,u=_[1],a=_[3]===void 0?we:_[3]==='"'?xt:bt):a===xt||a===bt?a=we:a===ft||a===yt?a=Le:(a=we,o=void 0);const S=a===we&&e[d+1].startsWith("/>")?" ":"";n+=a===Le?c+Qt:g>=0?(s.push(u),c.slice(0,g)+_t+c.slice(g)+fe+S):c+fe+(g===-2?d:S)}return[St(e,n+(e[i]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]};class Ne{constructor({strings:t,_$litType$:i},s){let o;this.parts=[];let n=0,a=0;const d=t.length-1,c=this.parts,[u,_]=Xt(t,i);if(this.el=Ne.createElement(u,s),Se.currentNode=this.el.content,i===2||i===3){const g=this.el.content.firstChild;g.replaceWith(...g.childNodes)}for(;(o=Se.nextNode())!==null&&c.length<d;){if(o.nodeType===1){if(o.hasAttributes())for(const g of o.getAttributeNames())if(g.endsWith(_t)){const y=_[a++],S=o.getAttribute(g).split(fe),A=/([.?@])?(.*)/.exec(y);c.push({type:1,index:n,name:A[2],strings:S,ctor:A[1]==="."?ti:A[1]==="?"?ii:A[1]==="@"?si:Ze}),o.removeAttribute(g)}else g.startsWith(fe)&&(c.push({type:6,index:n}),o.removeAttribute(g));if(wt.test(o.tagName)){const g=o.textContent.split(fe),y=g.length-1;if(y>0){o.textContent=Ke?Ke.emptyScript:"";for(let S=0;S<y;S++)o.append(g[S],He()),Se.nextNode(),c.push({type:2,index:++n});o.append(g[y],He())}}}else if(o.nodeType===8)if(o.data===vt)c.push({type:2,index:n});else{let g=-1;for(;(g=o.data.indexOf(fe,g+1))!==-1;)c.push({type:7,index:n}),g+=fe.length-1}n++}}static createElement(t,i){const s=xe.createElement("template");return s.innerHTML=t,s}}function ze(e,t,i=e,s){var a,d;if(t===$e)return t;let o=s!==void 0?(a=i._$Co)==null?void 0:a[s]:i._$Cl;const n=Oe(t)?void 0:t._$litDirective$;return(o==null?void 0:o.constructor)!==n&&((d=o==null?void 0:o._$AO)==null||d.call(o,!1),n===void 0?o=void 0:(o=new n(e),o._$AT(e,i,s)),s!==void 0?(i._$Co??(i._$Co=[]))[s]=o:i._$Cl=o),o!==void 0&&(t=ze(e,o._$AS(e,t.values),o,s)),t}class ei{constructor(t,i){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=i}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:i},parts:s}=this._$AD,o=((t==null?void 0:t.creationScope)??xe).importNode(i,!0);Se.currentNode=o;let n=Se.nextNode(),a=0,d=0,c=s[0];for(;c!==void 0;){if(a===c.index){let u;c.type===2?u=new Ie(n,n.nextSibling,this,t):c.type===1?u=new c.ctor(n,c.name,c.strings,this,t):c.type===6&&(u=new oi(n,this,t)),this._$AV.push(u),c=s[++d]}a!==(c==null?void 0:c.index)&&(n=Se.nextNode(),a++)}return Se.currentNode=xe,o}p(t){let i=0;for(const s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,i),i+=s.strings.length-2):s._$AI(t[i])),i++}}class Ie{get _$AU(){var t;return((t=this._$AM)==null?void 0:t._$AU)??this._$Cv}constructor(t,i,s,o){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=t,this._$AB=i,this._$AM=s,this.options=o,this._$Cv=(o==null?void 0:o.isConnected)??!0}get parentNode(){let t=this._$AA.parentNode;const i=this._$AM;return i!==void 0&&(t==null?void 0:t.nodeType)===11&&(t=i.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,i=this){t=ze(this,t,i),Oe(t)?t===p||t==null||t===""?(this._$AH!==p&&this._$AR(),this._$AH=p):t!==this._$AH&&t!==$e&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):Yt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==p&&Oe(this._$AH)?this._$AA.nextSibling.data=t:this.T(xe.createTextNode(t)),this._$AH=t}$(t){var n;const{values:i,_$litType$:s}=t,o=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=Ne.createElement(St(s.h,s.h[0]),this.options)),s);if(((n=this._$AH)==null?void 0:n._$AD)===o)this._$AH.p(i);else{const a=new ei(o,this),d=a.u(this.options);a.p(i),this.T(d),this._$AH=a}}_$AC(t){let i=$t.get(t.strings);return i===void 0&&$t.set(t.strings,i=new Ne(t)),i}k(t){it(this._$AH)||(this._$AH=[],this._$AR());const i=this._$AH;let s,o=0;for(const n of t)o===i.length?i.push(s=new Ie(this.O(He()),this.O(He()),this,this.options)):s=i[o],s._$AI(n),o++;o<i.length&&(this._$AR(s&&s._$AB.nextSibling,o),i.length=o)}_$AR(t=this._$AA.nextSibling,i){var s;for((s=this._$AP)==null?void 0:s.call(this,!1,!0,i);t!==this._$AB;){const o=mt(t).nextSibling;mt(t).remove(),t=o}}setConnected(t){var i;this._$AM===void 0&&(this._$Cv=t,(i=this._$AP)==null||i.call(this,t))}}class Ze{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,i,s,o,n){this.type=1,this._$AH=p,this._$AN=void 0,this.element=t,this.name=i,this._$AM=o,this.options=n,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=p}_$AI(t,i=this,s,o){const n=this.strings;let a=!1;if(n===void 0)t=ze(this,t,i,0),a=!Oe(t)||t!==this._$AH&&t!==$e,a&&(this._$AH=t);else{const d=t;let c,u;for(t=n[0],c=0;c<n.length-1;c++)u=ze(this,d[s+c],i,c),u===$e&&(u=this._$AH[c]),a||(a=!Oe(u)||u!==this._$AH[c]),u===p?t=p:t!==p&&(t+=(u??"")+n[c+1]),this._$AH[c]=u}a&&!o&&this.j(t)}j(t){t===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class ti extends Ze{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===p?void 0:t}}class ii extends Ze{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==p)}}class si extends Ze{constructor(t,i,s,o,n){super(t,i,s,o,n),this.type=5}_$AI(t,i=this){if((t=ze(this,t,i,0)??p)===$e)return;const s=this._$AH,o=t===p&&s!==p||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,n=t!==p&&(s===p||o);o&&this.element.removeEventListener(this.name,this,s),n&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){var i;typeof this._$AH=="function"?this._$AH.call(((i=this.options)==null?void 0:i.host)??this.element,t):this._$AH.handleEvent(t)}}class oi{constructor(t,i,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=i,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){ze(this,t)}}const ot=Re.litHtmlPolyfillSupport;ot==null||ot(Ne,Ie),(Re.litHtmlVersions??(Re.litHtmlVersions=[])).push("3.3.2");const ni=(e,t,i)=>{const s=(i==null?void 0:i.renderBefore)??t;let o=s._$litPart$;if(o===void 0){const n=(i==null?void 0:i.renderBefore)??null;s._$litPart$=o=new Ie(t.insertBefore(He(),n),n,void 0,i??{})}return o._$AI(e),o};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const Ce=globalThis;let z=class extends Me{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){var i;const t=super.createRenderRoot();return(i=this.renderOptions).renderBefore??(i.renderBefore=t.firstChild),t}update(t){const i=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=ni(i,this.renderRoot,this.renderOptions)}connectedCallback(){var t;super.connectedCallback(),(t=this._$Do)==null||t.setConnected(!0)}disconnectedCallback(){var t;super.disconnectedCallback(),(t=this._$Do)==null||t.setConnected(!1)}render(){return $e}};z._$litElement$=!0,z.finalized=!0,(Ot=Ce.litElementHydrateSupport)==null||Ot.call(Ce,{LitElement:z});const nt=Ce.litElementPolyfillSupport;nt==null||nt({LitElement:z}),(Ce.litElementVersions??(Ce.litElementVersions=[])).push("4.2.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const R=e=>(t,i)=>{i!==void 0?i.addInitializer(()=>{customElements.define(e,t)}):customElements.define(e,t)};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const ai={attribute:!0,type:String,converter:Ve,reflect:!1,hasChanged:tt},ri=(e=ai,t,i)=>{const{kind:s,metadata:o}=i;let n=globalThis.litPropertyMetadata.get(o);if(n===void 0&&globalThis.litPropertyMetadata.set(o,n=new Map),s==="setter"&&((e=Object.create(e)).wrapped=!0),n.set(i.name,e),s==="accessor"){const{name:a}=i;return{set(d){const c=t.get.call(this);t.set.call(this,d),this.requestUpdate(a,c,e,!0,d)},init(d){return d!==void 0&&this.C(a,void 0,e,d),d}}}if(s==="setter"){const{name:a}=i;return function(d){const c=this[a];t.call(this,d),this.requestUpdate(a,c,e,!0,d)}}throw Error("Unsupported decorator location: "+s)};function h(e){return(t,i)=>typeof i=="object"?ri(e,t,i):((s,o,n)=>{const a=o.hasOwnProperty(n);return o.constructor.createProperty(n,s),a?Object.getOwnPropertyDescriptor(o,n):void 0})(e,t,i)}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function m(e){return h({...e,state:!0,attribute:!1})}const Ge={en:{"panel.title":"RoomMind","panel.subtitle":"Climate management","panel.tab.rooms":"Rooms","panel.tab.settings":"Settings","panel.loading":"Loading...","panel.no_areas":"No areas configured in Home Assistant.","panel.no_areas_hint":"Add areas in HA settings to get started.","panel.stat.rooms":"Rooms","panel.stat.heating":"Heating","panel.stat.cooling":"Cooling","panel.hide_room":"Hide","panel.unhide":"Show","panel.hidden_rooms":"Hidden rooms","panel.floor_other":"Other","panel.reorder":"Reorder rooms","panel.reorder_done":"Done","room.back":"Back to rooms","room.section.climate_mode":"Climate Mode","room.section.schedule":"Schedule & Temperatures","room.section.devices":"Devices","room.delete":"Delete room","room.deleting":"Deleting...","room.saving":"Saving...","room.saved":"Saved","room.error_saving":"Error saving","room.confirm_delete":'Remove RoomMind configuration for "{name}"?',"room.error_save_fallback":"Failed to save configuration","room.error_delete_fallback":"Failed to delete configuration","room.alias.placeholder":"Custom display name","room.alias.clear":"Reset to area name","override.label":"Temporary Override","override.comfort":"Comfort","override.eco":"Eco","override.custom":"Custom","override.target":"Target:","override.activate_for":"Activate for:","override.error_set":"Failed to set override","override.error_clear":"Failed to clear override","hero.target":"Target","hero.override":"Override","hero.remaining":"{time} remaining","hero.humidity":"{value}% humidity","hero.trv_setpoint":"Thermostat set to {value}{unit}","hero.waiting":"Waiting for sensor data...","hero.not_configured":"Not configured yet","card.target":"Target","card.waiting":"Waiting for data...","card.humidity":"{value}% humidity","card.thermostat":"Thermostat","card.thermostats":"Thermostats","card.ac":"AC","card.acs":"ACs","card.climate_device":"climate device","card.climate_devices":"climate devices","card.temp_sensor":"temp sensor","card.temp_sensors":"temp sensors","card.no_climate":"No climate devices","card.tap_configure":"Tap to configure","card.mpc_active":"MPC active","card.mpc_learning":"MPC learning","card.not_controlled":"Not controlled by RoomMind","mode.auto":"Auto","mode.auto_desc":"Heats & cools automatically based on target temperature","mode.heat_only":"Heat Only","mode.heat_only_desc":"Only uses thermostats, ACs stay off","mode.cool_only":"Cool Only","mode.cool_only_desc":"Only uses ACs, thermostats stay off","mode.heating":"Heating","mode.cooling":"Cooling","mode.idle":"Standby","schedule.add_schedule":"Add schedule","schedule.select_schedule":"Select schedule helper","schedule.create_helper_hint":"Create new schedule helper in HA settings","schedule.selector_label":"Schedule selector entity","schedule.selector_value_boolean":"Current: {value}","schedule.selector_value_number":"Current value: {value}","schedule.selector_warning":"Multiple schedules but no selector set. Only the first will be used.","schedule.off_action_label":"Action when schedule is off","schedule.off_action_eco":"Use eco temperature","schedule.off_action_off":"Turn off devices","schedule.state_active":"Active","schedule.state_inactive":"Inactive","schedule.state_unreachable":"Unreachable","schedule.no_schedules":"No schedules configured","schedule.done":"Done","schedule.view_comfort":"Comfort: {temp}{unit}","schedule.view_eco":"Eco: {temp}{unit}","schedule.view_selector":"Active schedule selected by: {name}","schedule.view_selector_prefix":"Active schedule selected by:","schedule.help_header":"How do schedules work?","schedule.help_temps_title":"How is the target temperature determined?","schedule.help_temps":"The target temperature follows this priority chain:","schedule.help_temps_1":"<strong>Manual override</strong> – A temporary boost/eco/custom override always takes highest priority.","schedule.help_temps_2":"<strong>Block temperature</strong> – If the active schedule block has a <code>temperature</code> value in its data, that value is used.","schedule.help_temps_3":'<strong>Comfort temperature</strong> – If the schedule is "on" but the block has no temperature, the comfort fallback temperature below is used.',"schedule.help_temps_4":'<strong>Eco temperature</strong> – When the schedule is "off" (outside all time blocks), the eco temperature is used.',"schedule.help_block_title":"Setting temperature per time block","schedule.help_block":"You can set a specific temperature for each time block by adding a <code>temperature</code> value in the schedule's YAML configuration:","schedule.help_block_note":"If a block has no <code>temperature</code> data, the comfort fallback temperature is used instead.","schedule.help_split_title":"Separate heating/cooling targets per block","schedule.help_split":"For auto-mode rooms, you can set separate heating and cooling targets per time block using <code>heat_temperature</code> and <code>cool_temperature</code>:","schedule.help_split_note":"If only one is set, the other falls back to the room's comfort temperature. These keys take priority over <code>temperature</code> when present.","schedule.help_multi_title":"Multiple schedules","schedule.help_multi":"You can add multiple schedules and switch between them using a <strong>selector entity</strong>. This can be an <code>input_boolean</code> (toggles between schedule 1 and 2) or an <code>input_number</code> (selects by number). Without a selector entity, only the first schedule is used.","schedule.column_comfort":"Comfort","schedule.column_eco":"Eco","schedule.row_heat":"Heat","schedule.row_cool":"Cool","schedule.view_heat":"Heat: {comfort} / {eco}{unit}","schedule.view_cool":"Cool: {comfort} / {eco}{unit}","schedule.comfort_hint_auto":"Comfort: target when schedule is on. Eco: target when schedule is off. Rows set the target for heating and cooling.","schedule.comfort_label":"Fallback comfort temperature","schedule.eco_label":"Eco temperature","schedule.comfort_hint":'Used when schedule is "on" but no temperature is set in the block',"schedule.from_schedule":"{temp}{unit} from schedule","schedule.fallback":"{temp}{unit} (fallback)","schedule.eco_detail":"{temp}{unit} (eco)","devices.climate_entities":"Climate entities","devices.temp_sensors":"Temperature sensors","devices.humidity_sensors":"Humidity sensors","devices.no_climate":"No climate entities found in this area.","devices.no_temp_sensors":"No temperature sensors found in this area.","devices.no_humidity_sensors":"No humidity sensors found in this area.","devices.window_sensors":"Window / door sensors","devices.no_window_sensors":"No window/door sensors found in this area.","devices.window_open_delay":"Delay before pausing","devices.window_close_delay":"Delay before resuming","devices.add_entity":"Add entity","devices.done":"Done","devices.other_area":"Other area","devices.type_thermostat":"Thermostat","devices.type_ac":"AC","devices.heating_system_type":"Heating System Type","devices.heating_system_type_info":"After heating stops, radiators and especially underfloor systems continue to release stored heat. RoomMind accounts for this residual heat to avoid overshooting and improve model accuracy. Underfloor rooms also get longer minimum run times.","devices.system_type_none":"Standard (no residual heat)","devices.system_type_radiator":"Radiator","devices.system_type_underfloor":"Underfloor Heating","devices.underfloor_delay_hint":"Underfloor heating has long restart times. A window-open delay of at least 5 minutes is recommended to avoid unnecessary shutoffs.","hero.window_open":"Window open – paused","card.window_open":"Window open","settings.general_title":"General","settings.group_by_floor":"Group rooms by floor","settings.climate_control_active":"Climate control active","settings.climate_control_hint":"When disabled, RoomMind continues to monitor all sensors and train the model, but will not send any commands to your heating or cooling devices.","settings.learning_title":"Model Training","settings.learning_hint":"When paused, RoomMind stops collecting new measurement data and training the thermal model. Existing model data is preserved.","settings.learning_exceptions":"Exceptions","settings.learning_room_paused":"room paused","settings.learning_rooms_paused":"rooms paused","settings.sensors_title":"Sensors & Data Sources","settings.control_title":"Control","settings.outdoor_sensor":"Outdoor Temperature","settings.outdoor_sensor_label":"Outdoor temperature sensor","settings.outdoor_current":"Currently {temp}{unit} outside","settings.outdoor_waiting":"Waiting for sensor data...","settings.outdoor_humidity_sensor":"Outdoor Humidity","settings.outdoor_humidity_label":"Outdoor humidity sensor","settings.outdoor_humidity_current":"Currently {value}% outside","settings.smart_control":"Smart Climate Control","settings.smart_control_hint":"Configure outdoor temperature limits for heating and cooling.","settings.outdoor_cooling_min":"Minimum outdoor temp for cooling","settings.outdoor_cooling_min_hint":"AC stays off when outdoor temperature is below this value","settings.outdoor_heating_max":"Maximum outdoor temp for heating","settings.outdoor_heating_max_hint":"Heating stays off when outdoor temperature exceeds this value","settings.saving":"Saving...","settings.saved":"Saved","settings.error":"Error saving","devices.using_builtin_sensor":"Using thermostat's built-in sensor","settings.climate_intelligence":"Climate Intelligence","settings.control_mode":"Control Mode","settings.control_mode_simple":"Simple (Bang-Bang)","settings.control_mode_mpc":"Intelligent (MPC)","settings.control_mode_hint":"MPC learns your room's thermal behavior for optimal control","settings.comfort_weight":"Priority","settings.comfort_weight_comfort":"Comfort","settings.comfort_weight_efficiency":"Efficiency","settings.weather_entity":"Weather Forecast","settings.weather_entity_hint":"Optional: enables predictive outdoor temperature planning","settings.prediction_enabled":"Temperature prediction","settings.prediction_enabled_hint":"Show predicted temperature trend in analytics charts. Disable if you experience slow performance.","vacation.title":"Vacation Mode","vacation.hint":"Sets all rooms to a setback temperature until the end date.","vacation.active_label":"Vacation mode active","vacation.end_date":"End date & time","vacation.setback_temp":"Setback temperature","vacation.banner_title":"Vacation mode active","vacation.banner_detail":"{temp}{unit} until {date}","vacation.deactivate":"Deactivate","tabs.analytics":"Analytics","analytics.select_room":"Select Room","analytics.temperature":"Temperature","analytics.target":"Target","analytics.prediction":"Prediction","analytics.outdoor":"Outdoor","analytics.model_status":"Model Status","analytics.confidence":"Confidence","analytics.heating_rate":"Heating Strength","analytics.cooling_rate":"Cooling Strength","analytics.solar_gain":"Solar Gain","analytics.time_constant":"Time Constant","analytics.samples":"Samples","analytics.prediction_accuracy":"Prediction Accuracy","analytics.avg_deviation":"Avg. Deviation","analytics.data_sources":"Data Sources","analytics.data_points":"Data Points","analytics.control_mode":"Control Mode","analytics.control_mode_mpc":"MPC active","analytics.control_mode_bangbang":"MPC learning","analytics.last_model_update":"Last Model Update","analytics.accuracy_idle":"Accuracy (Idle)","analytics.accuracy_heating":"Accuracy (Heating)","analytics.info.accuracy_idle":"How precisely the model predicts temperature when neither heating nor cooling is active. A lower value means the model understands your room's natural heat loss well. This is the first value to improve because idle data is collected continuously.","analytics.info.accuracy_heating":"How precisely the model predicts temperature during active heating. This value stays high initially because the model needs real heating cycles to learn from. Once your heating has run a few times, this value will drop and MPC control becomes available.","analytics.info.confidence":"Overall model readiness for intelligent MPC control, combining two factors: data quantity (how many idle and active-mode samples have been collected) and prediction accuracy (how precise the temperature forecasts are). Confidence starts at 0% and rises as the model collects data and learns. Around 50% means enough idle data but still waiting for heating/cooling cycles. Above 80% means the model has enough data and accurate predictions — MPC control becomes available. 100% is the theoretical maximum when predictions are as accurate as physically possible.","analytics.info.time_constant":"How long it takes your room to naturally cool down halfway toward the outdoor temperature when heating is off. A longer time constant means better insulation — the room holds warmth longer. A short time constant means the room cools quickly. The model learns this by observing temperature drops during idle periods.","analytics.info.heating_rate":"How strongly your heating affects the room temperature. A higher value means your heating system warms the room faster relative to its thermal mass. The model learns this by observing how quickly the temperature rises during active heating, and uses it to predict how long heating needs to run.","analytics.info.cooling_rate":"How strongly your AC affects the room temperature. A higher value means the AC cools the room faster relative to its thermal mass. The model learns this by observing how quickly the temperature drops during active cooling, and uses it to predict how long the AC needs to run.","analytics.info.solar_gain":"The estimated effect of solar radiation through windows on room temperature. The model learns this by observing how the room warms during sunny periods when heating is off. Rooms with large south-facing windows will have higher values. The model uses this to reduce heating when solar gain is expected.","analytics.info.data_sources":"Number of measurement samples used for model training.","analytics.info.data_points":"Total number of observations the model has been trained on. More data points generally lead to better predictions. The model collects a new data point roughly every 3 minutes while RoomMind is running.","analytics.no_data":"No data yet — model is learning","analytics.loading":"Loading analytics...","settings.reset_title":"Reset Thermal Data","settings.reset_hint":"Clear learned thermal model data and history. The model will start learning from scratch.","settings.reset_all_label":"All rooms","settings.reset_all_hint":"Clear thermal data and history for all rooms at once.","settings.reset_all_btn":"Reset all","settings.reset_all_confirm":"Clear all learned thermal data and history for ALL rooms? All models will start learning from scratch.","settings.reset_room_label":"Individual room","settings.reset_room_hint":"Select a room to clear its thermal data and history.","settings.reset_room_confirm":"Clear all learned thermal data and history for this room? The model will start learning from scratch.","settings.reset_room_select":"Select room","settings.reset_btn":"Reset","settings.reset_no_rooms":"No configured rooms.","analytics.range_1d":"Today","analytics.range_2d":"2 days","analytics.range_7d":"Week","analytics.range_30d":"Month","analytics.export":"Measurements","analytics.heating_period":"Heating","analytics.cooling_period":"Cooling","analytics.window_open_period":"Window open","analytics.chart_info_title":"How to read this chart","analytics.exported":"Exported!","analytics.copy_diagnostics":"Model diagnostics","analytics.export_download":"Download file","analytics.export_clipboard":"Copy to clipboard","analytics.copied_to_clipboard":"Copied!","analytics.range_from":"From","analytics.range_to":"To","analytics.chart_info_body":`**Lines:** The solid orange line shows the measured room temperature. The green dashed line is the target temperature from your schedule. The blue dotted line is the model's temperature prediction.

**Shaded areas:** Red shading marks heating periods, blue marks cooling, and teal marks times when a window was open.

**Future forecast (right of the 'now' line):** The green dashed line shows the upcoming schedule targets for the next 3 hours. The blue dotted line shows the predicted temperature trend.

**Prediction modes:** When 'MPC active' is shown, the prediction uses the full MPC optimizer with intelligent pre-heating/pre-cooling. While the model is still learning, a simpler simulation is used.

**Limitations:** The prediction assumes current conditions stay constant (outdoor temperature, window state). The simulation accuracy depends on how well the thermal model has learned your room — early on, predictions may be less accurate. Once MPC activates, predictions become significantly more reliable.`,"presence.title":"Presence Detection","presence.hint":"Uses eco temperature when nobody is home.","presence.hint_detail":"When enabled, all rooms switch to eco temperature as soon as none of the configured persons are home. You can optionally restrict per room which persons are relevant.","presence.add_person":"Add person","presence.add_entity":"Add presence entity","presence.person_label":"Person","presence.banner_title":"Nobody home","presence.banner_detail":"All rooms set to eco temperature","presence.banner_detail_off":"All devices turned off","room.section.presence":"Presence","presence.room_help_header":"How does per-room presence work?","presence.room_help_body":"Select which persons are relevant for this room. The room switches to eco temperature when none of the selected persons are home. Without selection, the global rule applies: eco when nobody is home.","presence.state_home":"Home","presence.state_away":"Away","presence.room_none_assigned":"Global rule — eco when nobody is home","presence.away_action_label":"Action when nobody is home","presence.away_action_eco":"Use eco temperature","presence.away_action_off":"Turn off devices","card.presence_away":"Away","valve_protection.title":"Valve Protection","valve_protection.hint":"Periodically opens idle TRV valves briefly to prevent seizing or calcification.","valve_protection.interval_label":"Cycle interval","valve_protection.interval_suffix":"days","valve_protection.interval_hint":"How long a valve can be idle before being cycled (1–90 days)","mold.title":"Mold Risk Protection","mold.detection":"Mold Detection","mold.detection_desc":"Receive notifications when humidity indicates mold risk","mold.threshold":"Humidity threshold (%)","mold.threshold_hint":"Alert when room humidity stays above this value","mold.sustained":"Sustained duration (minutes)","mold.sustained_hint":"Alert only after risk persists for this long","mold.cooldown":"Notification cooldown (minutes)","mold.cooldown_hint":"Minimum time between repeated alerts per room","mold.target_person":"Person","mold.target_when_always":"Always","mold.target_when_home":"Only when home","mold.prevention":"Mold Prevention","mold.prevention_desc":"Automatically raise temperature to reduce mold risk","mold.intensity":"Intensity","mold.intensity_light":"Light (+{delta}{unit})","mold.intensity_medium":"Medium (+{delta}{unit})","mold.intensity_strong":"Strong (+{delta}{unit})","mold.intensity_hint":"Warmer air reduces surface humidity on cold walls. Light is usually sufficient for moderate risk, Strong can lower surface humidity by up to 8–10% — but uses noticeably more energy.","mold.prevention_notify":"Notify when prevention activates","mold.prevention_notify_hint":"Also send a notification when prevention activates (temperature raised)","mold.notifications_title":"Notifications","mold.notifications_enabled":"Enable notifications","mold.notifications_enabled_hint":"When disabled, no notifications are sent — neither to devices nor to the HA sidebar.","mold.notifications_beta_hint":"Beta. Will be reworked in a future update.","mold.notifications_desc":"Choose which devices receive mold risk alerts. Without targets, alerts appear in the HA sidebar.","mold.add_target_label":"Add notification device","mold.add_target_hint":"Type the entity ID if your device is not listed (e.g. notify.mobile_app_...). You can find it under Settings → Devices → your phone → Notify entity.","mold.target_unnamed":"Unnamed device","card.mold_warning":"Mold risk","card.mold_critical":"Mold danger!","card.mold_prevention":"Mold prevention +{delta}{unit}","room.mold_surface_rh":"Est. surface humidity: {value}%"},de:{"panel.title":"RoomMind","panel.subtitle":"Klimasteuerung","panel.tab.rooms":"Räume","panel.tab.settings":"Einstellungen","panel.loading":"Laden...","panel.no_areas":"Keine Bereiche in Home Assistant konfiguriert.","panel.no_areas_hint":"Bereiche in den HA-Einstellungen anlegen.","panel.stat.rooms":"Räume","panel.stat.heating":"Heizen","panel.stat.cooling":"Kühlen","panel.hide_room":"Ausblenden","panel.unhide":"Einblenden","panel.hidden_rooms":"Ausgeblendete Räume","panel.floor_other":"Sonstige","panel.reorder":"Räume sortieren","panel.reorder_done":"Fertig","room.back":"Zurück zu den Räumen","room.section.climate_mode":"Klimamodus","room.section.schedule":"Zeitplan & Temperaturen","room.section.devices":"Geräte","room.delete":"Raum löschen","room.deleting":"Wird gelöscht...","room.saving":"Speichern...","room.saved":"Gespeichert","room.error_saving":"Fehler beim Speichern","room.confirm_delete":'RoomMind-Konfiguration für "{name}" entfernen?',"room.error_save_fallback":"Konfiguration konnte nicht gespeichert werden","room.error_delete_fallback":"Konfiguration konnte nicht gelöscht werden","room.alias.placeholder":"Eigener Anzeigename","room.alias.clear":"Auf Bereichsname zurücksetzen","override.label":"Temporärer Override","override.comfort":"Komfort","override.eco":"Eco","override.custom":"Individuell","override.target":"Ziel:","override.activate_for":"Aktivieren für:","override.error_set":"Override konnte nicht gesetzt werden","override.error_clear":"Override konnte nicht aufgehoben werden","hero.target":"Ziel","hero.override":"Override","hero.remaining":"noch {time}","hero.humidity":"{value}% Luftfeuchtigkeit","hero.trv_setpoint":"Thermostat auf {value}{unit}","hero.waiting":"Warte auf Sensordaten...","hero.not_configured":"Noch nicht konfiguriert","card.target":"Ziel","card.waiting":"Warte auf Daten...","card.humidity":"{value}% Luftfeuchtigkeit","card.thermostat":"Thermostat","card.thermostats":"Thermostate","card.ac":"Klimaanlage","card.acs":"Klimaanlagen","card.climate_device":"Klimagerät","card.climate_devices":"Klimageräte","card.temp_sensor":"Temperatursensor","card.temp_sensors":"Temperatursensoren","card.no_climate":"Keine Klimageräte","card.tap_configure":"Tippen zum Konfigurieren","card.mpc_active":"MPC aktiv","card.mpc_learning":"MPC lernt","card.not_controlled":"Nicht von RoomMind gesteuert","mode.auto":"Automatisch","mode.auto_desc":"Heizt und kühlt automatisch basierend auf der Zieltemperatur","mode.heat_only":"Nur Heizen","mode.heat_only_desc":"Nutzt nur Thermostate, Klimaanlagen bleiben aus","mode.cool_only":"Nur Kühlen","mode.cool_only_desc":"Nutzt nur Klimaanlagen, Thermostate bleiben aus","mode.heating":"Heizen","mode.cooling":"Kühlen","mode.idle":"Standby","schedule.add_schedule":"Zeitplan hinzufügen","schedule.select_schedule":"Zeitplan-Helfer auswählen","schedule.create_helper_hint":"Neuen Zeitplan-Helfer in HA erstellen","schedule.selector_label":"Zeitplan-Auswahl","schedule.selector_value_boolean":"Aktuell: {value}","schedule.selector_value_number":"Aktueller Wert: {value}","schedule.selector_warning":"Mehrere Zeitpläne, aber keine Auswahl-Entity gesetzt. Nur der erste wird verwendet.","schedule.off_action_label":"Aktion wenn Zeitplan aus","schedule.off_action_eco":"Eco-Temperatur verwenden","schedule.off_action_off":"Geräte ausschalten","schedule.state_active":"Aktiv","schedule.state_inactive":"Inaktiv","schedule.state_unreachable":"Nicht erreichbar","schedule.no_schedules":"Keine Zeitpläne konfiguriert","schedule.done":"Fertig","schedule.view_comfort":"Komfort: {temp}{unit}","schedule.view_eco":"Eco: {temp}{unit}","schedule.view_selector":"Aktiver Zeitplan gewählt durch: {name}","schedule.view_selector_prefix":"Aktiver Zeitplan gewählt durch:","schedule.help_header":"Wie funktionieren Zeitpläne?","schedule.help_temps_title":"Wie wird die Zieltemperatur bestimmt?","schedule.help_temps":"Die Zieltemperatur folgt dieser Prioritätskette:","schedule.help_temps_1":"<strong>Manueller Override</strong> – Ein temporärer Komfort-/Eco-/Individueller Override hat immer die höchste Priorität.","schedule.help_temps_2":"<strong>Block-Temperatur</strong> – Wenn der aktive Zeitblock einen <code>temperature</code>-Wert in seinen Daten hat, wird dieser verwendet.","schedule.help_temps_3":'<strong>Komforttemperatur</strong> – Wenn der Zeitplan "an" ist, aber der Block keine Temperatur hat, wird die Komfort-Fallback-Temperatur verwendet.',"schedule.help_temps_4":'<strong>Eco-Temperatur</strong> – Wenn der Zeitplan "aus" ist (außerhalb aller Zeitblöcke), wird die Eco-Temperatur verwendet.',"schedule.help_block_title":"Temperatur pro Zeitblock setzen","schedule.help_block":"Du kannst für jeden Zeitblock eine eigene Temperatur setzen, indem du einen <code>temperature</code>-Wert in der YAML-Konfiguration des Zeitplans angibst:","schedule.help_block_note":"Wenn ein Block keinen <code>temperature</code>-Wert hat, wird stattdessen die Komfort-Fallback-Temperatur verwendet.","schedule.help_split_title":"Getrennte Heiz-/Kühlziele pro Block","schedule.help_split":"Für Räume im Auto-Modus kannst du pro Zeitblock separate Heiz- und Kühlziele mit <code>heat_temperature</code> und <code>cool_temperature</code> setzen:","schedule.help_split_note":"Wenn nur eines gesetzt ist, wird das andere auf die Komforttemperatur des Raumes zurückgesetzt. Diese Schlüssel haben Vorrang vor <code>temperature</code>.","schedule.help_multi_title":"Mehrere Zeitpläne","schedule.help_multi":"Du kannst mehrere Zeitpläne hinzufügen und mit einer <strong>Auswahl-Entity</strong> zwischen ihnen wechseln. Das kann ein <code>input_boolean</code> (wechselt zwischen Zeitplan 1 und 2) oder ein <code>input_number</code> (wählt nach Nummer) sein. Ohne Auswahl-Entity wird nur der erste Zeitplan verwendet.","schedule.column_comfort":"Komfort","schedule.column_eco":"Eco","schedule.row_heat":"Heizen","schedule.row_cool":"Kühlen","schedule.view_heat":"Heizen: {comfort} / {eco}{unit}","schedule.view_cool":"Kühlen: {comfort} / {eco}{unit}","schedule.comfort_hint_auto":"Komfort: Ziel wenn Zeitplan an. Eco: Ziel wenn Zeitplan aus. Zeilen: Ziel für Heizen bzw. Kühlen.","schedule.comfort_label":"Komfort-Fallback-Temperatur","schedule.eco_label":"Eco-Temperatur","schedule.comfort_hint":'Wird verwendet wenn der Zeitplan "an" ist, aber keine Temperatur im Block gesetzt ist',"schedule.from_schedule":"{temp}{unit} vom Zeitplan","schedule.fallback":"{temp}{unit} (Fallback)","schedule.eco_detail":"{temp}{unit} (Eco)","devices.climate_entities":"Klimageräte","devices.temp_sensors":"Temperatursensoren","devices.humidity_sensors":"Feuchtigkeitssensoren","devices.no_climate":"Keine Klimageräte in diesem Bereich gefunden.","devices.no_temp_sensors":"Keine Temperatursensoren in diesem Bereich gefunden.","devices.no_humidity_sensors":"Keine Feuchtigkeitssensoren in diesem Bereich gefunden.","devices.window_sensors":"Fenster- / Türsensoren","devices.no_window_sensors":"Keine Fenster-/Türsensoren in diesem Bereich gefunden.","devices.window_open_delay":"Verzögerung vor Pause","devices.window_close_delay":"Verzögerung vor Wiederaufnahme","devices.add_entity":"Entität hinzufügen","devices.done":"Fertig","devices.other_area":"Anderer Bereich","devices.type_thermostat":"Thermostat","devices.type_ac":"Klimaanlage","devices.heating_system_type":"Heizungstyp","devices.heating_system_type_info":"Nach dem Abschalten geben Heizkörper und besonders Fußbodenheizungen gespeicherte Wärme weiter ab. RoomMind berücksichtigt diese Nachlaufwärme, um Überschwingen zu vermeiden und die Modellgenauigkeit zu verbessern. Fußbodenheizungen erhalten außerdem längere Mindestlaufzeiten.","devices.system_type_none":"Standard (kein Nachlauf)","devices.system_type_radiator":"Heizkörper","devices.system_type_underfloor":"Fußbodenheizung","devices.underfloor_delay_hint":"Fußbodenheizung hat lange Anlaufzeiten. Eine Fenster-Verzögerung von mindestens 5 Minuten wird empfohlen, um unnötige Abschaltungen zu vermeiden.","hero.window_open":"Fenster offen – pausiert","card.window_open":"Fenster offen","settings.general_title":"Allgemein","settings.group_by_floor":"Räume nach Etagen gruppieren","settings.climate_control_active":"Klimasteuerung aktiv","settings.climate_control_hint":"Wenn deaktiviert, überwacht RoomMind weiterhin alle Sensoren und trainiert das Modell, steuert aber keine Heizungen oder Klimaanlagen mehr an.","settings.learning_title":"Modell-Training","settings.learning_hint":"Wenn pausiert, sammelt RoomMind keine neuen Messdaten und trainiert das thermische Modell nicht weiter. Bestehende Modelldaten bleiben erhalten.","settings.learning_exceptions":"Ausnahmen","settings.learning_room_paused":"Raum pausiert","settings.learning_rooms_paused":"Räume pausiert","settings.sensors_title":"Sensoren & Datenquellen","settings.control_title":"Steuerung","settings.outdoor_sensor":"Außentemperatur","settings.outdoor_sensor_label":"Außentemperatursensor","settings.outdoor_current":"Aktuell {temp}{unit} draußen","settings.outdoor_waiting":"Warte auf Sensordaten...","settings.outdoor_humidity_sensor":"Außenluftfeuchtigkeit","settings.outdoor_humidity_label":"Außenluftfeuchtigkeitssensor","settings.outdoor_humidity_current":"Aktuell {value}% draußen","settings.smart_control":"Intelligente Klimasteuerung","settings.smart_control_hint":"Außentemperaturgrenzen für Heiz- und Kühlentscheidungen konfigurieren.","settings.outdoor_cooling_min":"Mindest-Außentemperatur für Kühlung","settings.outdoor_cooling_min_hint":"Klimaanlage bleibt aus wenn Außentemperatur unter diesem Wert","settings.outdoor_heating_max":"Maximal-Außentemperatur für Heizung","settings.outdoor_heating_max_hint":"Heizung bleibt aus wenn Außentemperatur über diesem Wert","settings.saving":"Speichern...","settings.saved":"Gespeichert","settings.error":"Fehler beim Speichern","devices.using_builtin_sensor":"Nutzt den eingebauten Thermostat-Sensor","settings.climate_intelligence":"Klimaintelligenz","settings.control_mode":"Steuerungsmodus","settings.control_mode_simple":"Einfach (Ein/Aus)","settings.control_mode_mpc":"Intelligent (MPC)","settings.control_mode_hint":"MPC lernt das thermische Verhalten deiner Räume für optimale Steuerung","settings.comfort_weight":"Priorität","settings.comfort_weight_comfort":"Komfort","settings.comfort_weight_efficiency":"Effizienz","settings.weather_entity":"Wettervorhersage","settings.weather_entity_hint":"Optional: ermöglicht vorausschauende Außentemperaturplanung","settings.prediction_enabled":"Temperaturvorhersage","settings.prediction_enabled_hint":"Zeigt den vorhergesagten Temperaturverlauf im Analyse-Diagramm. Bei langsamer Performance deaktivieren.","vacation.title":"Urlaubsmodus","vacation.hint":"Setzt alle Räume auf eine Absenktemperatur bis zum Enddatum.","vacation.active_label":"Urlaubsmodus aktiv","vacation.end_date":"Enddatum & Uhrzeit","vacation.setback_temp":"Absenktemperatur","vacation.banner_title":"Urlaubsmodus aktiv","vacation.banner_detail":"{temp}{unit} bis {date}","vacation.deactivate":"Deaktivieren","tabs.analytics":"Analyse","analytics.select_room":"Raum auswählen","analytics.temperature":"Temperatur","analytics.target":"Ziel","analytics.prediction":"Vorhersage","analytics.outdoor":"Außen","analytics.model_status":"Modellstatus","analytics.confidence":"Konfidenz","analytics.heating_rate":"Heizstärke","analytics.cooling_rate":"Kühlstärke","analytics.solar_gain":"Solargewinn","analytics.time_constant":"Zeitkonstante","analytics.samples":"Datenpunkte","analytics.prediction_accuracy":"Vorhersagegenauigkeit","analytics.avg_deviation":"Durchschn. Abweichung","analytics.data_sources":"Datenquellen","analytics.data_points":"Datenpunkte","analytics.control_mode":"Steuerungsmodus","analytics.control_mode_mpc":"MPC aktiv","analytics.control_mode_bangbang":"MPC wird trainiert","analytics.last_model_update":"Letztes Modell-Update","analytics.accuracy_idle":"Genauigkeit (Leerlauf)","analytics.accuracy_heating":"Genauigkeit (Heizen)","analytics.info.accuracy_idle":"Wie genau das Modell die Temperatur vorhersagt, wenn weder geheizt noch gekühlt wird. Ein niedrigerer Wert bedeutet, dass das Modell den natürlichen Wärmeverlust deines Raums gut versteht. Dieser Wert verbessert sich als erstes, da Leerlauf-Daten kontinuierlich gesammelt werden.","analytics.info.accuracy_heating":"Wie genau das Modell die Temperatur während des aktiven Heizens vorhersagt. Dieser Wert bleibt anfangs hoch, da das Modell echte Heizzyklen zum Lernen braucht. Sobald deine Heizung ein paar Mal gelaufen ist, sinkt dieser Wert und die intelligente MPC-Steuerung wird verfügbar.","analytics.info.confidence":"Gesamte Modellreife für die intelligente MPC-Steuerung, basierend auf zwei Faktoren: Datenmenge (wie viele Leerlauf- und Aktiv-Messwerte gesammelt wurden) und Vorhersagegenauigkeit (wie präzise die Temperaturprognosen sind). Die Konfidenz startet bei 0% und steigt mit zunehmenden Daten. Etwa 50% bedeutet: genug Leerlaufdaten, aber noch zu wenig Heiz-/Kühlzyklen. Über 80% bedeutet: genug Daten und genaue Vorhersagen — MPC-Steuerung wird verfügbar. 100% ist das theoretische Maximum, wenn die Vorhersagen so genau wie physikalisch möglich sind.","analytics.info.time_constant":"Wie lange es dauert, bis sich die Raumtemperatur bei ausgeschalteter Heizung halbwegs der Außentemperatur annähert. Eine längere Zeitkonstante bedeutet bessere Dämmung — der Raum hält die Wärme länger. Eine kurze Zeitkonstante bedeutet schnelles Auskühlen. Das Modell lernt diesen Wert, indem es Temperaturabfälle im Leerlauf beobachtet.","analytics.info.heating_rate":"Wie stark deine Heizung die Raumtemperatur beeinflusst. Ein höherer Wert bedeutet, dass dein Heizsystem den Raum schneller erwärmt relativ zur thermischen Masse. Das Modell lernt dies durch Beobachtung der Temperaturanstiege beim Heizen und nutzt es um vorherzusagen, wie lange geheizt werden muss.","analytics.info.cooling_rate":"Wie stark deine Klimaanlage die Raumtemperatur beeinflusst. Ein höherer Wert bedeutet schnellere Kühlung relativ zur thermischen Masse. Das Modell lernt dies durch Beobachtung der Temperaturabfälle bei aktiver Kühlung und nutzt es um vorherzusagen, wie lange gekühlt werden muss.","analytics.info.solar_gain":"Der geschätzte Effekt der Sonneneinstrahlung durch Fenster auf die Raumtemperatur. Wird gelernt, indem beobachtet wird, wie sich der Raum bei Sonnenschein erwärmt, wenn nicht geheizt wird. Räume mit großen Südfenstern haben höhere Werte. Das Modell nutzt dies um die Heizung zu reduzieren, wenn Solargewinn erwartet wird.","analytics.info.data_sources":"Anzahl der Messwerte, die für das Modelltraining verwendet werden.","analytics.info.data_points":"Gesamtzahl der Beobachtungen, mit denen das Modell trainiert wurde. Mehr Datenpunkte führen in der Regel zu besseren Vorhersagen. Das Modell sammelt etwa alle 3 Minuten einen neuen Datenpunkt während RoomMind läuft.","analytics.no_data":"Noch keine Daten — Modell lernt","analytics.loading":"Analyse wird geladen...","settings.reset_title":"Thermische Daten zurücksetzen","settings.reset_hint":"Gelernte thermische Modelldaten und Verlauf löschen. Das Modell beginnt von vorne zu lernen.","settings.reset_all_label":"Alle Räume","settings.reset_all_hint":"Thermische Daten und Verlauf für alle Räume auf einmal löschen.","settings.reset_all_btn":"Alle zurücksetzen","settings.reset_all_confirm":"Alle gelernten thermischen Daten und Verlauf für ALLE Räume löschen? Alle Modelle beginnen von vorne zu lernen.","settings.reset_room_label":"Einzelner Raum","settings.reset_room_hint":"Wähle einen Raum, um dessen thermische Daten und Verlauf zu löschen.","settings.reset_room_confirm":"Alle gelernten thermischen Daten und Verlauf für diesen Raum löschen? Das Modell beginnt von vorne zu lernen.","settings.reset_room_select":"Raum auswählen","settings.reset_btn":"Zurücksetzen","settings.reset_no_rooms":"Keine konfigurierten Räume.","analytics.range_1d":"Heute","analytics.range_2d":"2 Tage","analytics.range_7d":"Woche","analytics.range_30d":"Monat","analytics.export":"Messdaten","analytics.heating_period":"Heizen","analytics.cooling_period":"Kühlung","analytics.window_open_period":"Fenster offen","analytics.chart_info_title":"So liest du dieses Diagramm","analytics.exported":"Exportiert!","analytics.copy_diagnostics":"Modell-Diagnose","analytics.export_download":"Datei herunterladen","analytics.export_clipboard":"In Zwischenablage kopieren","analytics.copied_to_clipboard":"Kopiert!","analytics.range_from":"Von","analytics.range_to":"Bis","analytics.chart_info_body":`**Linien:** Die durchgezogene orangene Linie zeigt die gemessene Raumtemperatur. Die grüne gestrichelte Linie ist die Zieltemperatur aus deinem Zeitplan. Die blaue gepunktete Linie ist die Temperaturvorhersage des Modells.

**Schattierte Bereiche:** Rote Schattierung markiert Heizperioden, blaue Kühlung und türkise Bereiche zeigen an, wenn ein Fenster offen war.

**Zukunftsprognose (rechts der 'Jetzt'-Linie):** Die grüne gestrichelte Linie zeigt die kommenden Zieltemperaturen für die nächsten 3 Stunden. Die blaue gepunktete Linie zeigt den vorhergesagten Temperaturverlauf.

**Vorhersage-Modus:** Wenn 'MPC aktiv' angezeigt wird, nutzt die Vorhersage den vollständigen MPC-Optimizer mit intelligentem Vorheizen/-kühlen. Solange das Modell noch lernt, wird eine einfachere Simulation verwendet.

**Einschränkungen:** Die Vorhersage nimmt an, dass aktuelle Bedingungen konstant bleiben (Außentemperatur, Fensterstatus). Die Genauigkeit hängt davon ab, wie gut das Modell deinen Raum bereits gelernt hat — anfangs können die Vorhersagen ungenau sein. Sobald MPC aktiviert wird, werden die Vorhersagen deutlich zuverlässiger.`,"presence.title":"Anwesenheitserkennung","presence.hint":"Eco-Temperatur wenn niemand zu Hause ist.","presence.hint_detail":"Wenn aktiviert, werden alle Räume auf Eco-Temperatur gesetzt, sobald keine der konfigurierten Personen zu Hause ist. Pro Raum kann optional eingeschränkt werden, welche Personen relevant sind.","presence.add_person":"Person hinzufügen","presence.add_entity":"Präsenz-Entity hinzufügen","presence.person_label":"Person","presence.banner_title":"Niemand zu Hause","presence.banner_detail":"Alle Räume auf Eco-Temperatur","presence.banner_detail_off":"Alle Geräte ausgeschaltet","room.section.presence":"Anwesenheit","presence.room_help_header":"Wie funktioniert die Raum-Anwesenheit?","presence.room_help_body":"Wähle aus, welche Personen für diesen Raum relevant sind. Der Raum schaltet auf Eco-Temperatur, wenn keine der ausgewählten Personen zu Hause ist. Ohne Auswahl greift die globale Regel: Eco wenn niemand zu Hause ist.","presence.state_home":"Zu Hause","presence.state_away":"Abwesend","presence.room_none_assigned":"Globale Regel — Eco wenn niemand zu Hause ist","presence.away_action_label":"Aktion wenn niemand zuhause","presence.away_action_eco":"Eco-Temperatur verwenden","presence.away_action_off":"Geräte ausschalten","card.presence_away":"Abwesend","valve_protection.title":"Ventilschutz","valve_protection.hint":"Bewegt inaktive TRV-Ventile regelmäßig kurz, um Festsitzen oder Verkalkung zu verhindern.","valve_protection.interval_label":"Zyklusintervall","valve_protection.interval_suffix":"Tage","valve_protection.interval_hint":"Wie lange ein Ventil inaktiv sein darf, bevor es bewegt wird (1–90 Tage)","mold.title":"Schimmelschutz","mold.detection":"Schimmelerkennung","mold.detection_desc":"Benachrichtigung bei Schimmelgefahr durch hohe Luftfeuchtigkeit","mold.threshold":"Feuchtigkeitsschwelle (%)","mold.threshold_hint":"Warnung wenn die Raumluftfeuchte diesen Wert dauerhaft überschreitet","mold.sustained":"Mindestdauer (Minuten)","mold.sustained_hint":"Warnung erst nach anhaltender Überschreitung","mold.cooldown":"Benachrichtigungspause (Minuten)","mold.cooldown_hint":"Mindestabstand zwischen wiederholten Warnungen pro Raum","mold.target_person":"Person","mold.target_when_always":"Immer","mold.target_when_home":"Nur wenn zuhause","mold.prevention":"Schimmelprävention","mold.prevention_desc":"Temperatur automatisch erhöhen um Schimmelrisiko zu senken","mold.intensity":"Intensität","mold.intensity_light":"Leicht (+{delta}{unit})","mold.intensity_medium":"Mittel (+{delta}{unit})","mold.intensity_strong":"Stark (+{delta}{unit})","mold.intensity_hint":"Wärmere Raumluft senkt die Oberflächenfeuchte an kalten Wänden. Leicht reicht meist bei moderatem Risiko, Stark kann die Oberflächenfeuchte um bis zu 8–10 % senken — verbraucht aber deutlich mehr Energie.","mold.prevention_notify":"Bei Aktivierung benachrichtigen","mold.prevention_notify_hint":"Auch benachrichtigen wenn die Prävention aktiviert wird (Temperaturerhöhung)","mold.notifications_title":"Benachrichtigungen","mold.notifications_enabled":"Benachrichtigungen aktivieren","mold.notifications_enabled_hint":"Wenn deaktiviert, werden keine Benachrichtigungen gesendet — weder an Geräte noch an die HA-Seitenleiste.","mold.notifications_beta_hint":"Beta. Wird in einem zukünftigen Update überarbeitet.","mold.notifications_desc":"Wähle die Geräte, die bei Schimmelgefahr benachrichtigt werden. Ohne Ziele erscheint eine Meldung in der HA-Seitenleiste.","mold.add_target_label":"Benachrichtigungsgerät hinzufügen","mold.add_target_hint":"Tippe die Entity-ID ein, falls dein Gerät nicht angezeigt wird (z.B. notify.mobile_app_...). Du findest sie unter Einstellungen → Geräte → dein Telefon → Notify-Entität.","mold.target_unnamed":"Unbenanntes Gerät","card.mold_warning":"Schimmelrisiko","card.mold_critical":"Schimmelgefahr!","card.mold_prevention":"Schimmelschutz +{delta}{unit}","room.mold_surface_rh":"Geschätzte Oberflächenfeuchte: {value}%"}};function r(e,t,i){let o=(Ge[t]??Ge[t.split("-")[0]]??Ge.en)[e]??Ge.en[e]??e;if(i)for(const[n,a]of Object.entries(i))o=o.replaceAll(`{${n}}`,String(a));return o}function li(e,t){if(e.area_id)return e.area_id;if(e.device_id&&t){const i=t[e.device_id];if(i!=null&&i.area_id)return i.area_id}return null}function Ct(e,t,i){return t?Object.values(t).filter(s=>li(s,i)===e):[]}function kt(e){switch(e){case"heating":return"mode-heating";case"cooling":return"mode-cooling";case"idle":return"mode-idle";default:return"mode-other"}}const ci={heating:"mode.heating",cooling:"mode.cooling",idle:"mode.idle"};function Et(e,t){return r(ci[e],t)}const At=D`
  .mode-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 14px;
    border-radius: 16px;
  }

  .mode-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .mode-heating {
    color: var(--warning-color, #ff9800);
    background: rgba(255, 152, 0, 0.12);
  }
  .mode-heating .mode-dot {
    background: var(--warning-color, #ff9800);
  }

  .mode-cooling {
    color: #2196f3;
    background: rgba(33, 150, 243, 0.12);
  }
  .mode-cooling .mode-dot {
    background: #2196f3;
  }

  .mode-idle {
    color: var(--secondary-text-color, #757575);
    background: rgba(0, 0, 0, 0.05);
  }
  .mode-idle .mode-dot {
    background: var(--disabled-text-color, #bdbdbd);
  }

  .mode-other {
    color: var(--secondary-text-color);
    background: rgba(0, 0, 0, 0.05);
  }
  .mode-other .mode-dot {
    background: var(--secondary-text-color);
  }
`,Tt="M11.83,9L15,12.16C15,12.11 15,12.05 15,12A3,3 0 0,0 12,9C11.94,9 11.89,9 11.83,9M7.53,9.8L9.08,11.35C9.03,11.56 9,11.77 9,12A3,3 0 0,0 12,15C12.22,15 12.44,14.97 12.65,14.92L14.2,16.47C13.53,16.8 12.79,17 12,17A5,5 0 0,1 7,12C7,11.21 7.2,10.47 7.53,9.8M2,4.27L4.28,6.55L4.73,7C3.08,8.3 1.78,10 1,12C2.73,16.39 7,19.5 12,19.5C13.55,19.5 15.03,19.2 16.38,18.66L16.81,19.08L19.73,22L21,20.73L3.27,3M12,7A5,5 0 0,1 17,12C17,12.64 16.87,13.26 16.64,13.82L19.57,16.75C21.07,15.5 22.27,13.86 23,12C21.27,7.61 17,4.5 12,4.5C10.6,4.5 9.26,4.75 8,5.2L10.17,7.35C10.74,7.13 11.35,7 12,7Z";function We(e){var t,i;return((i=(t=e.config)==null?void 0:t.unit_system)==null?void 0:i.temperature)==="°F"}function f(e){return We(e)?"°F":"°C"}function O(e,t){return We(t)?e*9/5+32:e}function ye(e,t){return We(t)?(e-32)*5/9:e}function ae(e,t){return We(t)?e*9/5:e}function P(e,t,i=1){return O(e,t).toFixed(i)}function re(e){return We(e)?"1":"0.5"}function H(e,t,i){return{min:String(Math.round(O(e,i))),max:String(Math.round(O(t,i)))}}var di=Object.defineProperty,hi=Object.getOwnPropertyDescriptor,ee=(e,t,i,s)=>{for(var o=s>1?void 0:s?hi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&di(t,i,o),o};let K=class extends z{constructor(){super(...arguments),this.config=null,this.climateEntityCount=0,this.tempSensorCount=0,this.controlMode="bangbang",this.climateControlActive=!0,this.reordering=!1,this.canMoveUp=!1,this.canMoveDown=!1}render(){var d,c,u,_,g,y,S;const e=this.climateEntityCount>0,t=(((c=(d=this.config)==null?void 0:d.thermostats)==null?void 0:c.length)??0)>0||(((_=(u=this.config)==null?void 0:u.acs)==null?void 0:_.length)??0)>0,i=this.config!==null&&t,s=(g=this.config)==null?void 0:g.live,o=s==null?void 0:s.mode,n=!i&&s&&(s.current_temp!==null||s.current_humidity!==null),a=i?o==="heating"?"accent-heating":o==="cooling"?"accent-cooling":"accent-idle":n?"accent-idle":"accent-unconfigured";return l`
      <ha-card
        @click=${this._onCardClick}
      >
        <div class="accent ${a}"></div>
        ${this.reordering?p:l`<ha-icon-button
              class="hide-btn"
              .path=${Tt}
              @click=${this._onHideClick}
            ></ha-icon-button>`}
        ${this.reordering?l`<div class="reorder-overlay">
              <div
                class="reorder-half left ${this.canMoveUp?"":"disabled"}"
                @click=${this._onMoveUp}
              >
                <ha-icon-button
                  .path=${"M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"}
                ></ha-icon-button>
              </div>
              <div
                class="reorder-half right ${this.canMoveDown?"":"disabled"}"
                @click=${this._onMoveDown}
              >
                <ha-icon-button
                  .path=${"M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"}
                ></ha-icon-button>
              </div>
            </div>`:p}
        <div class="card-inner">
          <div class="card-header">
            <h3 class="area-name">${((y=this.config)==null?void 0:y.display_name)||this.area.name}</h3>
            ${i&&s?l`
                  <span class="mode-pill ${kt(s.mode)}">
                    <span class="mode-dot"></span>
                    ${Et(s.mode,this.hass.language)}${s.heating_power>0&&s.heating_power<100?l` ${s.heating_power}%`:p}
                  </span>
                `:p}
          </div>

          ${i?this._renderConfigured():(S=this.config)!=null&&S.live&&(this.config.live.current_temp!==null||this.config.live.current_humidity!==null)?this._renderSensorOnly():this._renderUnconfigured(e)}
        </div>
      </ha-card>
    `}_renderConfigured(){var i;const e=(i=this.config)==null?void 0:i.live;if(!e)return l`<div class="waiting">${r("card.waiting",this.hass.language)}</div>`;const t=this.controlMode==="mpc";return l`
      <div class="temp-section">
        ${e.current_temp!==null?l`
              <span class="current-temp">${P(e.current_temp,this.hass)}</span>
              <span class="temp-unit">${f(this.hass)}</span>
            `:l`<span class="no-temp">--</span>`}
        ${this._renderTargetInfo(e)}
      </div>
      <div class="card-footer">
        <span class="humidity-info">
          ${e.current_humidity!==null?r("card.humidity",this.hass.language,{value:e.current_humidity.toFixed(0)}):p}
        </span>
        <span class="badge-row">
          ${e.mold_risk_level&&e.mold_risk_level!=="ok"?l`<span class="mold-badge ${e.mold_risk_level}">
                <ha-icon icon="mdi:water-alert"></ha-icon>
                ${e.mold_risk_level==="critical"?r("card.mold_critical",this.hass.language):r("card.mold_warning",this.hass.language)}
              </span>`:p}
          ${e.mold_prevention_active?l`<span class="mold-badge prevention">
                <ha-icon icon="mdi:shield-check"></ha-icon>
                ${r("card.mold_prevention",this.hass.language,{delta:ae(e.mold_prevention_delta,this.hass).toFixed(0),unit:f(this.hass)})}
              </span>`:p}
          ${t?l`<span class="mpc-badge ${e.mpc_active?"active":"learning"}">
                <ha-icon .icon=${e.mpc_active?"mdi:brain":"mdi:school-outline"}></ha-icon>
                ${e.mpc_active?r("card.mpc_active",this.hass.language):r("card.mpc_learning",this.hass.language)}
              </span>`:p}
        </span>
      </div>
      ${this.climateControlActive?p:l`<div class="uncontrolled-hint">${r("card.not_controlled",this.hass.language)}</div>`}
    `}_renderTargetInfo(e){var o;if(e.target_temp===null&&e.heat_target===null)return p;const s=(((o=this.config)==null?void 0:o.climate_mode)??"auto")==="auto"&&e.heat_target!=null&&e.cool_target!=null&&e.heat_target!==e.cool_target?l`<span class="target-value">${P(e.heat_target,this.hass)} – ${P(e.cool_target,this.hass)}${f(this.hass)}</span>`:l`<span class="target-value">${P(e.target_temp??e.heat_target,this.hass)}${f(this.hass)}</span>`;return l`
      <span class="target-info">
        ${r("card.target",this.hass.language)} ${s}
        ${e.override_active?l`<ha-icon class="override-icon" icon="mdi:timer-outline"></ha-icon>`:p}
        ${e.window_open?l`<ha-icon class="window-icon" icon="mdi:window-open-variant"></ha-icon>`:p}
        ${e.presence_away?l`<ha-icon class="away-icon" icon="mdi:home-off-outline"></ha-icon>`:p}
      </span>
    `}_renderSensorOnly(){const e=this.config.live;return l`
      <div class="temp-section">
        ${e.current_temp!==null?l`
              <span class="current-temp">${P(e.current_temp,this.hass)}</span>
              <span class="temp-unit">${f(this.hass)}</span>
            `:l`<span class="no-temp">--</span>`}
      </div>
      <div class="card-footer">
        <span class="humidity-info">
          ${e.current_humidity!==null?r("card.humidity",this.hass.language,{value:e.current_humidity.toFixed(0)}):p}
        </span>
        <span class="badge-row">
          ${e.mold_risk_level&&e.mold_risk_level!=="ok"?l`<span class="mold-badge ${e.mold_risk_level}">
                <ha-icon icon="mdi:water-alert"></ha-icon>
                ${e.mold_risk_level==="critical"?r("card.mold_critical",this.hass.language):r("card.mold_warning",this.hass.language)}
              </span>`:p}
        </span>
      </div>
    `}_renderUnconfigured(e){const t=this.hass.language;if(!e)return l`<div class="device-summary empty">${r("card.no_climate",t)}</div>`;const i=this.climateEntityCount,s=this.tempSensorCount;return l`
      <div class="device-summary">
        ${i} ${r(i!==1?"card.climate_devices":"card.climate_device",t)}${s>0?` · ${s} ${r(s!==1?"card.temp_sensors":"card.temp_sensor",t)}`:""}
      </div>
      <div class="configure-prompt">
        <span class="configure-text">${r("card.tap_configure",t)}</span>
        <span class="configure-arrow">\u203A</span>
      </div>
    `}_onCardClick(){this.dispatchEvent(new CustomEvent("area-selected",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}_onMoveUp(e){e.stopPropagation(),this.canMoveUp&&this.dispatchEvent(new CustomEvent("move-room-up",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}_onMoveDown(e){e.stopPropagation(),this.canMoveDown&&this.dispatchEvent(new CustomEvent("move-room-down",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}_onHideClick(e){e.stopPropagation(),this.dispatchEvent(new CustomEvent("hide-room",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}};K.styles=[At,D`
    :host {
      display: block;
    }

    ha-card {
      cursor: pointer;
      transition: box-shadow 0.2s ease, transform 0.15s ease;
      overflow: hidden;
      position: relative;
      height: 100%;
      box-sizing: border-box;
    }

    ha-card:hover {
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
      transform: translateY(-1px);
    }

    .hide-btn {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
      color: var(--secondary-text-color);
      opacity: 0;
      transition: opacity 0.2s ease;
      position: absolute;
      top: 8px;
      right: 8px;
    }

    ha-card:hover .hide-btn {
      opacity: 0.4;
    }

    .hide-btn:hover {
      opacity: 1 !important;
    }

    /* Colored left accent based on mode */
    .accent {
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
    }

    .accent-heating {
      background: var(--warning-color, #ff9800);
    }

    .accent-cooling {
      background: #2196f3;
    }

    .accent-idle {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .accent-unconfigured {
      background: transparent;
    }

    .card-inner {
      padding: 20px 20px 16px;
    }

    /* Header row: name + badge */
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .area-name {
      font-size: 15px;
      font-weight: 500;
      color: var(--primary-text-color);
      margin: 0;
      letter-spacing: 0.01em;
    }

    /* Card-specific mode-pill overrides (smaller than default) */
    .mode-pill {
      gap: 5px;
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 12px;
    }

    .mode-dot {
      width: 7px;
      height: 7px;
    }

    /* Temperature display */
    .temp-section {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin: 12px 0 0 0;
    }

    .current-temp {
      font-size: 36px;
      font-weight: 300;
      color: var(--primary-text-color);
      line-height: 1;
    }

    .temp-unit {
      font-size: 18px;
      font-weight: 300;
      color: var(--secondary-text-color);
    }

    .target-info {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-left: auto;
    }

    .target-value {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .override-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .window-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .away-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--info-color, #2196f3);
    }

    /* Footer row: humidity + MPC status */
    .card-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 8px;
      min-height: 20px;
    }

    .humidity-info {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .mpc-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mpc-badge.active {
      color: var(--success-color, #4caf50);
      background: rgba(76, 175, 80, 0.12);
    }

    .mpc-badge.learning {
      color: var(--secondary-text-color);
      background: rgba(158, 158, 158, 0.1);
    }

    .mold-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mold-badge.warning {
      color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.12);
    }

    .mold-badge.critical {
      color: var(--error-color, #db4437);
      background: rgba(219, 68, 55, 0.12);
    }

    .mold-badge.prevention {
      color: var(--info-color, #2196f3);
      background: rgba(33, 150, 243, 0.12);
    }

    .badge-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .no-temp {
      font-size: 24px;
      font-weight: 300;
      color: var(--secondary-text-color);
      line-height: 1;
    }

    .uncontrolled-hint {
      font-size: 11px;
      color: var(--disabled-text-color, #9e9e9e);
      margin-top: 6px;
    }

    .reorder-overlay {
      position: absolute;
      inset: 0;
      z-index: 2;
      display: flex;
      pointer-events: none;
      border-radius: inherit;
      overflow: hidden;
    }

    .reorder-half {
      pointer-events: auto;
      flex: 0 0 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 0.15s ease;
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.05);
    }

    .reorder-half.left {
      border-radius: inherit;
      border-top-right-radius: 0;
      border-bottom-right-radius: 0;
      border-right: 1px solid rgba(var(--rgb-primary-text-color, 0,0,0), 0.08);
    }

    .reorder-half.right {
      border-radius: inherit;
      border-top-left-radius: 0;
      border-bottom-left-radius: 0;
      border-left: 1px solid rgba(var(--rgb-primary-text-color, 0,0,0), 0.08);
      margin-left: auto;
    }

    .reorder-half:hover {
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.1);
    }

    .reorder-half ha-icon-button {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      pointer-events: none;
    }

    .reorder-half:hover ha-icon-button {
      color: var(--primary-text-color);
    }

    .reorder-half.disabled {
      opacity: 0.25;
      cursor: default;
    }

    .reorder-half.disabled:hover {
      background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.05);
    }

    /* Device summary for unconfigured cards */
    .device-summary {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 8px;
    }

    .device-summary.empty {
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
    }

    /* Configure prompt for unconfigured areas */
    .configure-prompt {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .configure-text {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .configure-arrow {
      font-size: 18px;
      color: var(--primary-color);
    }

    /* Waiting state */
    .waiting {
      font-size: 13px;
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
      margin-top: 8px;
    }
  `],ee([h({attribute:!1})],K.prototype,"area",2),ee([h({attribute:!1})],K.prototype,"config",2),ee([h({type:Number})],K.prototype,"climateEntityCount",2),ee([h({type:Number})],K.prototype,"tempSensorCount",2),ee([h({attribute:!1})],K.prototype,"hass",2),ee([h({type:String})],K.prototype,"controlMode",2),ee([h({type:Boolean})],K.prototype,"climateControlActive",2),ee([h({type:Boolean})],K.prototype,"reordering",2),ee([h({type:Boolean})],K.prototype,"canMoveUp",2),ee([h({type:Boolean})],K.prototype,"canMoveDown",2),K=ee([R("rs-area-card")],K);var pi=Object.defineProperty,ui=Object.getOwnPropertyDescriptor,de=(e,t,i,s)=>{for(var o=s>1?void 0:s?ui(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&pi(t,i,o),o};const mi="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",gi="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";let te=class extends z{constructor(){super(...arguments),this.config=null,this.climateControlActive=!0,this.overrideInfo=null,this._countdown="",this._editingName=!1,this._nameInput=""}disconnectedCallback(){super.disconnectedCallback(),this._clearCountdownTimer()}updated(e){(e.has("overrideInfo")||e.has("config"))&&this._updateCountdown()}_clearCountdownTimer(){this._countdownTimer&&(clearInterval(this._countdownTimer),this._countdownTimer=void 0)}_getOverrideUntil(){var e;return(e=this.overrideInfo)!=null&&e.active?this.overrideInfo.until:null}_updateCountdown(){if(this._clearCountdownTimer(),!this._getOverrideUntil()){this._countdown="";return}const t=()=>{const i=this._getOverrideUntil();if(!i){this._countdown="",this._clearCountdownTimer();return}const s=i-Date.now()/1e3;if(s<=0){this._countdown="",this._clearCountdownTimer();return}const o=Math.floor(s/3600),n=Math.floor(s%3600/60);this._countdown=o>0?`${o}h ${n}m`:`${n}m`};t(),this._countdownTimer=setInterval(t,3e4)}_getEffectiveOverride(){var e;return(e=this.overrideInfo)!=null&&e.active?this.overrideInfo:null}_renderTargetSection(e){var o,n;const t=e.target_temp,i=((o=this.hass)==null?void 0:o.language)??"en",s=this._getEffectiveOverride();if(s){const a=s.type==="boost"?"mdi:fire":s.type==="eco"?"mdi:leaf":"mdi:thermometer",d=s.type==="boost"?r("override.comfort",i):s.type==="eco"?r("override.eco",i):r("override.custom",i),c=`override-${s.type}`,u=s.temp??t;return l`
        <div class="hero-target">
          <div class="hero-target-label ${c}">
            <ha-icon icon=${a}></ha-icon>
            ${d} ${r("hero.override",i)}
          </div>
          <div class="hero-target-value">
            ${u!==null?l`${P(u,this.hass)}${f(this.hass)}`:"--"}
          </div>
          ${this._countdown?l`<div class="hero-target-countdown">${r("hero.remaining",i,{time:this._countdown})}</div>`:p}
        </div>
      `}if(t!==null||e.heat_target!=null&&e.cool_target!=null){const c=(((n=this.config)==null?void 0:n.climate_mode)??"auto")==="auto"&&e.heat_target!=null&&e.cool_target!=null&&e.heat_target!==e.cool_target?l`${P(e.heat_target,this.hass)} – ${P(e.cool_target,this.hass)}${f(this.hass)}`:l`${P(t??e.heat_target,this.hass)}${f(this.hass)}`;return l`
        <div class="hero-target">
          <div class="hero-target-label">${r("hero.target",i)}</div>
          <div class="hero-target-value">${c}</div>
        </div>
      `}return p}_onEditName(){var e;this._nameInput=((e=this.config)==null?void 0:e.display_name)||"",this._editingName=!0,this.updateComplete.then(()=>{const t=this.renderRoot.querySelector(".name-input");t==null||t.focus(),t==null||t.select()})}_onNameInput(e){this._nameInput=e.target.value}_onNameKeydown(e){e.key==="Enter"?this._onNameDone():e.key==="Escape"&&(this._editingName=!1)}_onNameDone(){const e=this._nameInput.trim();this.dispatchEvent(new CustomEvent("display-name-changed",{detail:{value:e},bubbles:!0,composed:!0})),this._editingName=!1}_onNameClear(){this.dispatchEvent(new CustomEvent("display-name-changed",{detail:{value:""},bubbles:!0,composed:!0})),this._editingName=!1,this._nameInput=""}render(){var s,o,n,a,d,c,u,_,g,y,S,A,M,F;const e=(s=this.config)==null?void 0:s.live,t=e==null?void 0:e.mode;return l`
      <ha-card>
        <div class="hero-accent ${e?t==="heating"?"hero-accent-heating":t==="cooling"?"hero-accent-cooling":"hero-accent-idle":"hero-accent-none"}"></div>
        <div class="hero-header">
          ${this._editingName?l`
                <div class="name-edit-row">
                  <input
                    class="name-input"
                    type="text"
                    .value=${this._nameInput}
                    placeholder=${r("room.alias.placeholder",((o=this.hass)==null?void 0:o.language)??"en")}
                    @input=${this._onNameInput}
                    @keydown=${this._onNameKeydown}
                  />
                  <ha-icon-button
                    class="name-done-btn"
                    .path=${gi}
                    @click=${this._onNameDone}
                  ></ha-icon-button>
                </div>
                ${(n=this.config)!=null&&n.display_name?l`<button class="name-clear-btn" @click=${this._onNameClear}>
                      ${r("room.alias.clear",((a=this.hass)==null?void 0:a.language)??"en")}
                    </button>`:p}
              `:l`
                <div class="name-row">
                  <h2 class="area-name">${((d=this.config)==null?void 0:d.display_name)||this.area.name}</h2>
                  <ha-icon-button
                    class="name-edit-btn"
                    .path=${mi}
                    @click=${this._onEditName}
                  ></ha-icon-button>
                </div>
              `}
          ${e?l`
                <span class="mode-pill ${kt(e.mode)}">
                  <span class="mode-dot"></span>
                  ${Et(e.mode,((c=this.hass)==null?void 0:c.language)??"en")}${e.heating_power>0&&e.heating_power<100?l` ${e.heating_power}%`:p}
                </span>
              `:p}
        </div>
        ${e?l`
              ${e.window_open?l`<div class="hero-window-open">
                    <ha-icon icon="mdi:window-open-variant"></ha-icon>
                    ${r("hero.window_open",((u=this.hass)==null?void 0:u.language)??"en")}
                  </div>`:p}
              <div class="hero-temps">
                ${e.current_temp!==null?l`
                      <span class="hero-current">${P(e.current_temp,this.hass)}</span>
                      <span class="hero-unit">${f(this.hass)}</span>
                    `:l`<span class="hero-current" style="opacity: 0.3">--</span>`}
                ${this._renderTargetSection(e)}
              </div>
              ${e.current_humidity!==null?l`<div class="hero-metric">
                    <ha-icon icon="mdi:water-percent"></ha-icon>
                    ${r("hero.humidity",((_=this.hass)==null?void 0:_.language)??"en",{value:e.current_humidity.toFixed(0)})}
                  </div>`:p}
              ${e.trv_setpoint!=null?l`<div class="hero-metric">
                    <ha-icon icon="mdi:radiator"></ha-icon>
                    ${r("hero.trv_setpoint",((g=this.hass)==null?void 0:g.language)??"en",{value:P(e.trv_setpoint,this.hass),unit:f(this.hass)})}
                  </div>`:p}
              ${e.mold_surface_rh!=null?l`<div class="hero-metric ${e.mold_risk_level==="critical"?"critical":e.mold_risk_level==="warning"?"warning":""}">
                    <ha-icon icon="mdi:water-alert"></ha-icon>
                    ${r("room.mold_surface_rh",((y=this.hass)==null?void 0:y.language)??"en",{value:String(e.mold_surface_rh.toFixed(0))})}
                  </div>`:p}
              ${e.mold_prevention_active?l`<div class="hero-metric info">
                    <ha-icon icon="mdi:shield-check"></ha-icon>
                    ${r("card.mold_prevention",((S=this.hass)==null?void 0:S.language)??"en",{delta:ae(e.mold_prevention_delta,this.hass).toFixed(0),unit:f(this.hass)})}
                  </div>`:p}
              ${this.climateControlActive?p:l`<div class="uncontrolled-hint">${r("card.not_controlled",((A=this.hass)==null?void 0:A.language)??"en")}</div>`}
            `:this.config?l`<div class="hero-no-data">${r("hero.waiting",((M=this.hass)==null?void 0:M.language)??"en")}</div>`:l`<div class="hero-no-data">${r("hero.not_configured",((F=this.hass)==null?void 0:F.language)??"en")}</div>`}
      </ha-card>
    `}};te.styles=[At,D`
      :host {
        display: block;
      }

      ha-card {
        padding: 28px 24px;
        position: relative;
        overflow: hidden;
      }

      .hero-accent {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
      }

      .hero-accent-heating {
        background: linear-gradient(90deg, var(--warning-color, #ff9800), #ffb74d);
      }

      .hero-accent-cooling {
        background: linear-gradient(90deg, #2196f3, #64b5f6);
      }

      .hero-accent-idle {
        background: linear-gradient(
          90deg,
          var(--disabled-text-color, #bdbdbd),
          #e0e0e0
        );
      }

      .hero-accent-none {
        background: var(--divider-color, #e0e0e0);
      }

      .hero-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
      }

      .area-name {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        margin: 0;
      }

      .hero-temps {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .hero-current {
        font-size: 48px;
        font-weight: 300;
        color: var(--primary-text-color);
        line-height: 1;
      }

      .hero-unit {
        font-size: 24px;
        font-weight: 300;
        color: var(--secondary-text-color);
      }

      .hero-target {
        margin-left: auto;
        text-align: right;
      }

      .hero-target-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .hero-target-value {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
      }

      /* Override-aware target styling */
      .hero-target-label.override-boost {
        color: var(--warning-color, #ff9800);
      }

      .hero-target-label.override-eco {
        color: #4caf50;
      }

      .hero-target-label.override-custom {
        color: #2196f3;
      }

      .hero-target-label ha-icon {
        --mdc-icon-size: 12px;
        vertical-align: middle;
      }

      .hero-target-countdown {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }

      .hero-metric {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 14px;
        color: var(--secondary-text-color);
        margin-top: 6px;
      }

      .hero-metric ha-icon {
        --mdc-icon-size: 16px;
        flex-shrink: 0;
      }

      .hero-metric.warning {
        color: var(--warning-color, #ff9800);
      }

      .hero-metric.critical {
        color: var(--error-color, #db4437);
      }

      .hero-metric.info {
        color: var(--info-color, #2196f3);
      }

      .hero-no-data {
        font-size: 14px;
        color: var(--disabled-text-color, #9e9e9e);
        font-style: italic;
        padding: 8px 0;
      }

      .hero-window-open {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        margin-bottom: 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.1);
      }

      .hero-window-open ha-icon {
        --mdc-icon-size: 18px;
      }

      .name-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-edit-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--secondary-text-color);
        opacity: 0;
        transition: opacity 0.15s;
      }

      .name-row:hover .name-edit-btn {
        opacity: 1;
      }

      @media (hover: none) {
        .name-edit-btn {
          opacity: 0.5;
        }
      }

      .name-edit-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-input {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        background: transparent;
        border: none;
        border-bottom: 2px solid var(--primary-color);
        outline: none;
        padding: 0 0 2px;
        width: 100%;
        font-family: inherit;
      }

      .name-done-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--primary-color);
      }

      .name-clear-btn {
        background: none;
        border: none;
        color: var(--secondary-text-color);
        font-size: 12px;
        cursor: pointer;
        padding: 2px 0;
        text-decoration: underline;
      }

      .uncontrolled-hint {
        font-size: 12px;
        color: var(--disabled-text-color, #9e9e9e);
        margin-top: 8px;
      }
    `],de([h({attribute:!1})],te.prototype,"hass",2),de([h({attribute:!1})],te.prototype,"area",2),de([h({attribute:!1})],te.prototype,"config",2),de([h({type:Boolean})],te.prototype,"climateControlActive",2),de([h({attribute:!1})],te.prototype,"overrideInfo",2),de([m()],te.prototype,"_countdown",2),de([m()],te.prototype,"_editingName",2),de([m()],te.prototype,"_nameInput",2),te=de([R("rs-hero-status")],te);var _i=Object.defineProperty,vi=Object.getOwnPropertyDescriptor,at=(e,t,i,s)=>{for(var o=s>1?void 0:s?vi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&_i(t,i,o),o};let je=class extends z{constructor(){super(...arguments),this.climateMode="auto",this.language="en"}render(){const e=this.language;return l`
      <div class="mode-grid">
        ${[{value:"auto",labelKey:"mode.auto",icon:"mdi:autorenew"},{value:"heat_only",labelKey:"mode.heat_only",icon:"mdi:fire"},{value:"cool_only",labelKey:"mode.cool_only",icon:"mdi:snowflake"}].map(i=>l`
            <button
              class="mode-card"
              ?active=${this.climateMode===i.value}
              @click=${()=>this._onModeClick(i.value)}
            >
              <ha-icon class="mode-card-icon" icon=${i.icon}></ha-icon>
              <div class="mode-card-label">${r(i.labelKey,e)}</div>
            </button>
          `)}
      </div>
    `}_onModeClick(e){this.dispatchEvent(new CustomEvent("mode-changed",{detail:{mode:e},bubbles:!0,composed:!0}))}};je.styles=D`
    :host {
      display: block;
    }

    .mode-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }

    .mode-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      padding: 14px 8px;
      border: 2px solid var(--divider-color, #e0e0e0);
      border-radius: 12px;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
      background: transparent;
      font-family: inherit;
      color: var(--primary-text-color);
      text-align: center;
    }

    .mode-card:hover {
      border-color: var(--primary-color, #03a9f4);
      box-shadow: 0 2px 8px rgba(3, 169, 244, 0.1);
    }

    .mode-card[active] {
      border-color: var(--primary-color, #03a9f4);
      background: rgba(3, 169, 244, 0.06);
      box-shadow: 0 2px 8px rgba(3, 169, 244, 0.12);
    }

    .mode-card-icon {
      --mdc-icon-size: 24px;
    }

    .mode-card[active] .mode-card-icon {
      color: var(--primary-color, #03a9f4);
    }

    .mode-card-label {
      font-weight: 500;
      font-size: 13px;
    }

    .mode-card[active] .mode-card-label {
      color: var(--primary-color, #03a9f4);
    }
  `,at([h({type:String})],je.prototype,"climateMode",2),at([h({type:String})],je.prototype,"language",2),je=at([R("rs-climate-mode-selector")],je);/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const fi={CHILD:2},yi=e=>(...t)=>({_$litDirective$:e,values:t});class bi{constructor(t){}get _$AU(){return this._$AM._$AU}_$AT(t,i,s){this._$Ct=t,this._$AM=i,this._$Ci=s}_$AS(t,i){return this.update(t,i)}update(t,i){return this.render(...i)}}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class rt extends bi{constructor(t){if(super(t),this.it=p,t.type!==fi.CHILD)throw Error(this.constructor.directiveName+"() can only be used in child bindings")}render(t){if(t===p||t==null)return this._t=void 0,this.it=t;if(t===$e)return t;if(typeof t!="string")throw Error(this.constructor.directiveName+"() called with a non-string value");if(t===this.it)return this._t;this.it=t;const i=[t];return i.raw=i,this._t={_$litType$:this.constructor.resultType,strings:i,values:[]}}}rt.directiveName="unsafeHTML",rt.resultType=1;const he=yi(rt);function pe(e){const t=e.detail;return(t==null?void 0:t.value)??e.target.value??""}function J(e,t){e.dispatchEvent(new CustomEvent("save-status",{detail:{status:t},bubbles:!0,composed:!0}))}function qe(e,t){e.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:!0,composed:!0,detail:{entityId:t}}))}var xi=Object.defineProperty,wi=Object.getOwnPropertyDescriptor,ie=(e,t,i,s)=>{for(var o=s>1?void 0:s?wi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&xi(t,i,o),o};let Z=class extends z{constructor(){super(...arguments),this.schedules=[],this.scheduleSelectorEntity="",this.activeScheduleIndex=0,this.comfortHeat=21,this.comfortCool=24,this.ecoHeat=17,this.ecoCool=27,this.climateMode="auto",this.editing=!1}render(){return this.editing?this._renderEditMode():this._renderViewMode()}_renderViewMode(){var i,s,o,n;const e=this.hass.language,t=this.schedules.length>=2;return l`
      ${this.schedules.length>0?l`
          <div class="schedule-list">
            ${this.schedules.map((a,d)=>{var g,y,S;const c=this._getScheduleState(d),u=(y=(g=this.hass)==null?void 0:g.states)==null?void 0:y[a.entity_id],_=((S=u==null?void 0:u.attributes)==null?void 0:S.friendly_name)||a.entity_id;return l`
                <div class="schedule-row ${c}">
                  ${t?l`<span class="schedule-number">${d+1}</span>`:p}
                  <span class="schedule-status-dot"></span>
                  <span class="schedule-name schedule-link" @click=${()=>qe(this,a.entity_id)}>${_}</span>
                  <span class="schedule-status">${this._getStatusText(d,c)}</span>
                </div>
              `})}
          </div>
        `:l`<div class="no-schedules">${r("schedule.no_schedules",e)}</div>`}

      ${this.climateMode==="auto"?l`
        <div class="view-temps">
          ${r("schedule.view_heat",e,{comfort:P(this.comfortHeat,this.hass),eco:P(this.ecoHeat,this.hass),unit:f(this.hass)})}
          \u00A0\u00B7\u00A0
          ${r("schedule.view_cool",e,{comfort:P(this.comfortCool,this.hass),eco:P(this.ecoCool,this.hass),unit:f(this.hass)})}
        </div>
      `:l`
        <div class="view-temps">
          ${r("schedule.view_comfort",e,{temp:P(this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat,this.hass),unit:f(this.hass)})}
          \u00A0\u00B7\u00A0
          ${r("schedule.view_eco",e,{temp:P(this.climateMode==="cool_only"?this.ecoCool:this.ecoHeat,this.hass),unit:f(this.hass)})}
        </div>
      `}

      ${this.scheduleSelectorEntity?l`<div class="view-selector-info">
            ${r("schedule.view_selector_prefix",e)}
            <span class="schedule-link" @click=${()=>qe(this,this.scheduleSelectorEntity)}>${((n=(o=(s=(i=this.hass)==null?void 0:i.states)==null?void 0:s[this.scheduleSelectorEntity])==null?void 0:o.attributes)==null?void 0:n.friendly_name)||this.scheduleSelectorEntity}</span>
          </div>`:p}
    `}_renderEditMode(){const e=this.hass.language,t=this.schedules.length>=2;return l`
      ${this._renderScheduleList(t)}
      ${this._renderAddSchedule()}
      ${this._renderSelectorSection()}

      ${this.climateMode==="auto"?l`
        <div class="temp-grid-auto">
          <div class="temp-grid-header"></div>
          <div class="temp-grid-header">${r("schedule.column_comfort",e)}</div>
          <div class="temp-grid-header">${r("schedule.column_eco",e)}</div>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:fire" style="--mdc-icon-size:16px"></ha-icon>
            ${r("schedule.row_heat",e)}
          </div>
          <ha-textfield type="number"
            .value=${String(O(this.comfortHeat,this.hass))}
            suffix=${f(this.hass)} step=${re(this.hass)}
            min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
            @change=${this._onComfortHeatChange}
          ></ha-textfield>
          <ha-textfield type="number"
            .value=${String(O(this.ecoHeat,this.hass))}
            suffix=${f(this.hass)} step=${re(this.hass)}
            min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
            @change=${this._onEcoHeatChange}
          ></ha-textfield>
          <div class="temp-grid-row-label">
            <ha-icon icon="mdi:snowflake" style="--mdc-icon-size:16px"></ha-icon>
            ${r("schedule.row_cool",e)}
          </div>
          <ha-textfield type="number"
            .value=${String(O(this.comfortCool,this.hass))}
            suffix=${f(this.hass)} step=${re(this.hass)}
            min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
            @change=${this._onComfortCoolChange}
          ></ha-textfield>
          <ha-textfield type="number"
            .value=${String(O(this.ecoCool,this.hass))}
            suffix=${f(this.hass)} step=${re(this.hass)}
            min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
            @change=${this._onEcoCoolChange}
          ></ha-textfield>
        </div>
      `:l`
        <div class="temp-inputs">
          <div class="temp-input-group">
            <ha-textfield type="number"
              label=${r("schedule.comfort_label",e)}
              suffix=${f(this.hass)} step=${re(this.hass)}
              .value=${String(O(this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat,this.hass))}
              min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
              @change=${this.climateMode==="cool_only"?this._onComfortCoolChange:this._onComfortHeatChange}
            ></ha-textfield>
          </div>
          <div class="temp-input-group">
            <ha-textfield type="number"
              label=${r("schedule.eco_label",e)}
              suffix=${f(this.hass)} step=${re(this.hass)}
              .value=${String(O(this.climateMode==="cool_only"?this.ecoCool:this.ecoHeat,this.hass))}
              min=${H(5,35,this.hass).min} max=${H(5,35,this.hass).max}
              @change=${this.climateMode==="cool_only"?this._onEcoCoolChange:this._onEcoHeatChange}
            ></ha-textfield>
          </div>
        </div>
      `}
      <div class="fallback-hint">
        ${this.climateMode==="auto"?r("schedule.comfort_hint_auto",e):r("schedule.comfort_hint",e)}
      </div>

      <ha-expansion-panel outlined header=${r("schedule.help_header",e)}>
        <div class="help-content">
          <p><strong>${r("schedule.help_temps_title",e)}</strong></p>
          <p>${r("schedule.help_temps",e)}</p>
          <ol style="margin: 4px 0 0 0; padding-left: 20px; font-size: 12px; line-height: 1.8">
            <li>${he(r("schedule.help_temps_1",e))}</li>
            <li>${he(r("schedule.help_temps_2",e))}</li>
            <li>${he(r("schedule.help_temps_3",e))}</li>
            <li>${he(r("schedule.help_temps_4",e))}</li>
          </ol>

          <p style="margin-top: 12px"><strong>${r("schedule.help_block_title",e)}</strong></p>
          <p>${he(r("schedule.help_block",e))}</p>
          <div class="yaml-block"><span class="yaml-key">schedule</span>:
  <span class="yaml-key">living_room_heating</span>:
    <span class="yaml-key">name</span>: <span class="yaml-value">Living Room Heating</span>
    <span class="yaml-key">monday</span>:
      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">23</span>
      - <span class="yaml-key">from</span>: <span class="yaml-value">"17:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"22:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">21.5</span></div>
          <p style="margin-top: 8px">${he(r("schedule.help_block_note",e))}</p>

          <p style="margin-top: 12px"><strong>${r("schedule.help_split_title",e)}</strong></p>
          <p>${he(r("schedule.help_split",e))}</p>
          <div class="yaml-block">      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">heat_temperature</span>: <span class="yaml-value">21</span>
          <span class="yaml-key">cool_temperature</span>: <span class="yaml-value">24</span></div>
          <p style="margin-top: 8px">${he(r("schedule.help_split_note",e))}</p>

          <p style="margin-top: 12px"><strong>${r("schedule.help_multi_title",e)}</strong></p>
          <p>${he(r("schedule.help_multi",e))}</p>
        </div>
      </ha-expansion-panel>

    `}_renderSelectorSection(){var s,o;const e=this.hass.language;if(!(this.schedules.length>=2))return p;const i=this.scheduleSelectorEntity?(o=(s=this.hass)==null?void 0:s.states)==null?void 0:o[this.scheduleSelectorEntity]:null;return l`
      <div class="selector-section">
        <label class="form-label">${r("schedule.selector_label",e)}</label>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.scheduleSelectorEntity}
          .includeDomains=${["input_boolean","input_number"]}
          allow-custom-entity
          @value-changed=${this._onSelectorEntityChange}
        ></ha-entity-picker>
        ${this.scheduleSelectorEntity&&i?l`
                <div class="selector-value">
                  ${this.scheduleSelectorEntity.startsWith("input_boolean.")?r("schedule.selector_value_boolean",e,{value:i.state==="on"?"On":"Off"}):r("schedule.selector_value_number",e,{value:i.state})}
                </div>
              `:p}
        ${this.schedules.length>1&&!this.scheduleSelectorEntity?l`
              <div class="selector-warning">
                <ha-icon icon="mdi:alert-outline"></ha-icon>
                ${r("schedule.selector_warning",e)}
              </div>
            `:p}
      </div>
    `}_renderScheduleList(e){const t=this.hass.language;return this.schedules.length===0?l`<div class="no-schedules">${r("schedule.no_schedules",t)}</div>`:l`
      <div class="schedule-list">
        ${this.schedules.map((i,s)=>{var d,c,u;const o=this._getScheduleState(s),n=(c=(d=this.hass)==null?void 0:d.states)==null?void 0:c[i.entity_id],a=((u=n==null?void 0:n.attributes)==null?void 0:u.friendly_name)||i.entity_id;return l`
            <div class="schedule-row ${o}">
              ${e?l`<span class="schedule-number">${s+1}</span>`:p}
              <span class="schedule-status-dot"></span>
              <span class="schedule-name">${a}</span>
              <span class="schedule-status">${this._getStatusText(s,o)}</span>
              <span class="schedule-controls">
                ${e&&s>0?l`
                      <ha-icon-button
                        .path=${"M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"}
                        @click=${()=>this._onMoveSchedule(s,-1)}
                      ></ha-icon-button>
                    `:p}
                ${e&&s<this.schedules.length-1?l`
                      <ha-icon-button
                        .path=${"M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z"}
                        @click=${()=>this._onMoveSchedule(s,1)}
                      ></ha-icon-button>
                    `:p}
                <ha-icon-button
                  .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                  @click=${()=>this._onRemoveSchedule(s)}
                ></ha-icon-button>
              </span>
            </div>
          `})}
      </div>
    `}_renderAddSchedule(){const e=this.hass.language,t=this._getAvailableScheduleEntities();return l`
      <div class="add-schedule-row">
        <ha-select
          .value=${""}
          .label=${r("schedule.select_schedule",e)}
          .options=${t.map(i=>{var s,o;return{value:i,label:((o=(s=this.hass.states[i])==null?void 0:s.attributes)==null?void 0:o.friendly_name)||i}})}
          @selected=${this._onAddSchedule}
          @closed=${i=>i.stopPropagation()}
          fixedMenuPosition
          naturalMenuWidth
        >
          ${t.map(i=>{var n;const s=this.hass.states[i],o=((n=s==null?void 0:s.attributes)==null?void 0:n.friendly_name)||i;return l`
              <ha-list-item value=${i}>
                ${o}
              </ha-list-item>
            `})}
        </ha-select>
        <a href="/config/helpers" target="_top" class="helper-link">
          ${r("schedule.create_helper_hint",e)}
        </a>
      </div>
    `}_getScheduleState(e){var i,s,o,n;if(this.schedules.length===0)return"inactive";if(e===this.activeScheduleIndex)return"active";if(!this.scheduleSelectorEntity)return e===0?"active":"unreachable";const t=(s=(i=this.hass)==null?void 0:i.states)==null?void 0:s[this.scheduleSelectorEntity];if(!t)return"inactive";if(this.scheduleSelectorEntity.startsWith("input_boolean."))return e<=1?"inactive":"unreachable";if(this.scheduleSelectorEntity.startsWith("input_number.")){const a=Number(((o=t.attributes)==null?void 0:o.min)??1),d=Number(((n=t.attributes)==null?void 0:n.max)??this.schedules.length),c=e+1;return c>=a&&c<=d?"inactive":"unreachable"}return"inactive"}_getStatusText(e,t){var a,d,c;const i=this.hass.language;if(t==="unreachable")return r("schedule.state_unreachable",i);if(t==="inactive")return r("schedule.state_inactive",i);const s=this.schedules[e],o=(d=(a=this.hass)==null?void 0:a.states)==null?void 0:d[s.entity_id];if(!o)return r("schedule.state_active",i);if(o.state==="on"){const u=(c=o.attributes)==null?void 0:c.temperature;return u!=null?r("schedule.from_schedule",i,{temp:String(u),unit:f(this.hass)}):r("schedule.fallback",i,{temp:P(this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat,this.hass),unit:f(this.hass)})}return r("schedule.eco_detail",i,{temp:P(this.climateMode==="cool_only"?this.ecoCool:this.ecoHeat,this.hass),unit:f(this.hass)})}_getScheduleEntities(){var e;return(e=this.hass)!=null&&e.states?Object.keys(this.hass.states).filter(t=>t.startsWith("schedule.")):[]}_getAvailableScheduleEntities(){const e=this._getScheduleEntities(),t=new Set(this.schedules.map(i=>i.entity_id));return e.filter(i=>!t.has(i))}_onAddSchedule(e){const t=pe(e);if(!t)return;const i=[...this.schedules,{entity_id:t}];this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:i},bubbles:!0,composed:!0})),requestAnimationFrame(()=>{e.target.value=""})}_onRemoveSchedule(e){const t=this.schedules.filter((i,s)=>s!==e);this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onMoveSchedule(e,t){const i=e+t;if(i<0||i>=this.schedules.length)return;const s=[...this.schedules],o=s[e];s[e]=s[i],s[i]=o,this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:s},bubbles:!0,composed:!0}))}_onSelectorEntityChange(e){var i;const t=((i=e.detail)==null?void 0:i.value)??"";this.dispatchEvent(new CustomEvent("schedule-selector-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onComfortHeatChange(e){const t=e.target,i=ye(parseFloat(t.value)||O(21,this.hass),this.hass);this.dispatchEvent(new CustomEvent("comfort-heat-changed",{detail:{value:i},bubbles:!0,composed:!0})),this.comfortCool<i&&this.dispatchEvent(new CustomEvent("comfort-cool-changed",{detail:{value:i},bubbles:!0,composed:!0}))}_onComfortCoolChange(e){const t=e.target,i=ye(parseFloat(t.value)||O(24,this.hass),this.hass);this.dispatchEvent(new CustomEvent("comfort-cool-changed",{detail:{value:i},bubbles:!0,composed:!0})),this.comfortHeat>i&&this.dispatchEvent(new CustomEvent("comfort-heat-changed",{detail:{value:i},bubbles:!0,composed:!0}))}_onEcoHeatChange(e){const t=e.target,i=ye(parseFloat(t.value)||O(17,this.hass),this.hass);this.dispatchEvent(new CustomEvent("eco-heat-changed",{detail:{value:i},bubbles:!0,composed:!0})),this.ecoCool<i&&this.dispatchEvent(new CustomEvent("eco-cool-changed",{detail:{value:i},bubbles:!0,composed:!0}))}_onEcoCoolChange(e){const t=e.target,i=ye(parseFloat(t.value)||O(27,this.hass),this.hass);this.dispatchEvent(new CustomEvent("eco-cool-changed",{detail:{value:i},bubbles:!0,composed:!0})),this.ecoHeat>i&&this.dispatchEvent(new CustomEvent("eco-heat-changed",{detail:{value:i},bubbles:!0,composed:!0}))}};Z.styles=D`
    :host {
      display: block;
    }

    .form-group {
      margin-bottom: 16px;
    }

    .form-group:last-child {
      margin-bottom: 0;
    }

    .form-label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    ha-select {
      width: 100%;
    }

    /* Selector section */
    .selector-section {
      margin-bottom: 16px;
    }

    .selector-value {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      padding-left: 4px;
    }

    .selector-warning {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      background: rgba(255, 152, 0, 0.08);
      color: var(--warning-color, #ff9800);
      font-size: 13px;
    }

    .selector-warning ha-icon {
      --mdc-icon-size: 18px;
      flex-shrink: 0;
    }

    /* Schedule list */
    .schedule-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 12px;
    }

    .schedule-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s, opacity 0.3s;
    }

    .schedule-row.active {
      background: rgba(76, 175, 80, 0.1);
    }

    .schedule-row.inactive {
      background: rgba(0, 0, 0, 0.04);
    }

    .schedule-row.unreachable {
      background: rgba(0, 0, 0, 0.02);
      opacity: 0.4;
    }

    .schedule-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 500;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--divider-color, #e0e0e0);
      color: var(--primary-text-color);
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-number {
      background: #4caf50;
      color: #fff;
    }

    .schedule-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-status-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .schedule-row.inactive .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-row.unreachable .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .schedule-link {
      cursor: pointer;
    }

    .schedule-link:hover {
      text-decoration: underline;
    }

    .schedule-row.active .schedule-name {
      color: var(--primary-text-color);
    }

    .schedule-row.inactive .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-status {
      font-size: 12px;
      white-space: nowrap;
    }

    .schedule-row.active .schedule-status {
      color: #2e7d32;
    }

    .schedule-row.inactive .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-controls {
      display: flex;
      align-items: center;
      gap: 2px;
      flex-shrink: 0;
    }

    .schedule-controls ha-icon-button {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
    }

    /* Add schedule row */
    .add-schedule-row {
      margin-top: 4px;
    }

    .add-schedule-row ha-select {
      width: 100%;
    }

    .helper-link {
      display: inline-block;
      margin-top: 4px;
      font-size: 12px;
      color: var(--primary-color);
      text-decoration: none;
    }

    .helper-link:hover {
      text-decoration: underline;
    }

    /* No schedules */
    .no-schedules {
      font-size: 13px;
      color: var(--secondary-text-color);
      padding: 12px 0;
      text-align: center;
    }

    /* Collapsible help */
    ha-expansion-panel {
      margin-top: 8px;
    }

    .help-content {
      padding: 0 12px 12px;
      font-size: 12px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }

    .help-content p {
      margin: 0 0 8px 0;
    }

    .help-content p:last-child {
      margin-bottom: 0;
    }

    .yaml-block {
      background: var(--primary-background-color, #f5f5f5);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: var(--code-font-family, monospace);
      font-size: 12px;
      line-height: 1.5;
      white-space: pre;
      overflow-x: auto;
      color: var(--primary-text-color);
    }

    .yaml-comment {
      color: var(--secondary-text-color);
    }

    .yaml-key {
      color: #0550ae;
    }

    .yaml-value {
      color: #0a3069;
    }

    .fallback-hint {
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      font-style: italic;
    }

    .temp-inputs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }

    .temp-input-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    ha-textfield {
      flex: 1;
    }

    /* View mode */
    .view-temps {
      display: flex;
      gap: 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .view-temps span {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .view-selector-info {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 8px;
    }

    .temp-grid-auto {
      display: grid;
      grid-template-columns: auto 1fr 1fr;
      gap: 8px 12px;
      align-items: center;
      margin-top: 16px;
    }
    .temp-grid-header {
      font-size: 12px;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.3px;
      text-align: center;
    }
    .temp-grid-row-label {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    @media (max-width: 600px) {
      .temp-grid-auto {
        grid-template-columns: 1fr 1fr;
      }
      .temp-grid-row-label {
        grid-column: 1 / -1;
        margin-top: 8px;
      }
      .temp-grid-header {
        display: none;
      }
    }

  `,ie([h({attribute:!1})],Z.prototype,"hass",2),ie([h({attribute:!1})],Z.prototype,"schedules",2),ie([h({type:String})],Z.prototype,"scheduleSelectorEntity",2),ie([h({type:Number})],Z.prototype,"activeScheduleIndex",2),ie([h({type:Number})],Z.prototype,"comfortHeat",2),ie([h({type:Number})],Z.prototype,"comfortCool",2),ie([h({type:Number})],Z.prototype,"ecoHeat",2),ie([h({type:Number})],Z.prototype,"ecoCool",2),ie([h({type:String})],Z.prototype,"climateMode",2),ie([h({type:Boolean})],Z.prototype,"editing",2),Z=ie([R("rs-schedule-settings")],Z);var $i=Object.defineProperty,Si=Object.getOwnPropertyDescriptor,G=(e,t,i,s)=>{for(var o=s>1?void 0:s?Si(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&$i(t,i,o),o};let U=class extends z{constructor(){super(...arguments),this.selectedThermostats=new Set,this.selectedAcs=new Set,this.selectedTempSensor="",this.selectedHumiditySensor="",this.selectedWindowSensors=new Set,this.windowOpenDelay=0,this.windowCloseDelay=0,this.heatingSystemType="",this.editing=!1,this._systemTypeInfoExpanded=!1,this._entityFilter=e=>{var i,s,o,n;const t=e.entity_id;if(this.selectedThermostats.has(t)||this.selectedAcs.has(t)||this.selectedTempSensor===t||this.selectedHumiditySensor===t||this.selectedWindowSensors.has(t))return!1;if(t.startsWith("sensor.")){const a=(s=(i=this.hass.states[t])==null?void 0:i.attributes)==null?void 0:s.device_class;if(a!=="temperature"&&a!=="humidity")return!1}if(t.startsWith("binary_sensor.")){const a=(n=(o=this.hass.states[t])==null?void 0:o.attributes)==null?void 0:n.device_class;if(a!=="window"&&a!=="door"&&a!=="opening")return!1}return!0}}render(){return this.editing?this._renderEditMode():this._renderViewMode()}_renderViewMode(){const e=this.selectedThermostats.size>0||this.selectedAcs.size>0,t=!!this.selectedTempSensor,i=!!this.selectedHumiditySensor;return l`
      ${e?l`
        <div class="device-group">
          <div class="section-subtitle">${r("devices.climate_entities",this.hass.language)}</div>
          ${[...this.selectedThermostats].map(s=>this._renderViewRow(s,"climate"))}
          ${[...this.selectedAcs].map(s=>this._renderViewRow(s,"climate"))}
        </div>
      `:p}

      ${t?l`
        <div class="device-group">
          <div class="section-subtitle">${r("devices.temp_sensors",this.hass.language)}</div>
          ${this._renderViewRow(this.selectedTempSensor,"temp")}
        </div>
      `:p}

      ${i?l`
        <div class="device-group">
          <div class="section-subtitle">${r("devices.humidity_sensors",this.hass.language)}</div>
          ${this._renderViewRow(this.selectedHumiditySensor,"humidity")}
        </div>
      `:p}

      ${this.selectedWindowSensors.size>0?l`
        <div class="device-group">
          <div class="section-subtitle">${r("devices.window_sensors",this.hass.language)}</div>
          ${[...this.selectedWindowSensors].map(s=>this._renderWindowViewRow(s))}
          ${this.windowOpenDelay||this.windowCloseDelay?l`
            <div class="delay-view">
              ${this.windowOpenDelay?l`${r("devices.window_open_delay",this.hass.language)}: ${this.windowOpenDelay}s`:p}
              ${this.windowOpenDelay&&this.windowCloseDelay?" · ":p}
              ${this.windowCloseDelay?l`${r("devices.window_close_delay",this.hass.language)}: ${this.windowCloseDelay}s`:p}
            </div>
          `:p}
        </div>
      `:p}

      ${this.heatingSystemType?l`
        <div class="device-group">
          <div class="section-subtitle">${r("devices.heating_system_type",this.hass.language)}</div>
          <div class="view-row">
            <span class="view-name">${this.heatingSystemType==="radiator"?r("devices.system_type_radiator",this.hass.language):this.heatingSystemType==="underfloor"?r("devices.system_type_underfloor",this.hass.language):this.heatingSystemType}</span>
          </div>
        </div>
      `:p}
    `}_renderViewRow(e,t){var d;const i=this.hass.states[e],s=((d=i==null?void 0:i.attributes)==null?void 0:d.friendly_name)||e,o=i==null?void 0:i.state,n=(i==null?void 0:i.attributes)??{};let a="";if(t==="climate"){const c=n.current_temperature;c!=null&&(a=`${c.toFixed(1)}°`)}else t==="temp"?o&&o!=="unknown"&&o!=="unavailable"&&(a=`${Number(o).toFixed(1)}${f(this.hass)}`):o&&o!=="unknown"&&o!=="unavailable"&&(a=`${Math.round(Number(o))}%`);return l`
      <div class="view-row">
        <span class="view-name entity-link" @click=${()=>qe(this,e)}>${s}</span>
        ${a?l`<span class="view-value">${a}</span>`:p}
      </div>
    `}_renderWindowViewRow(e){var o;const t=this.hass.states[e],i=((o=t==null?void 0:t.attributes)==null?void 0:o.friendly_name)||e,s=(t==null?void 0:t.state)==="on";return l`
      <div class="view-row">
        <span class="view-name entity-link" @click=${()=>qe(this,e)}>${i}</span>
        <span class="view-value" style="color: ${s?"var(--warning-color, #ff9800)":"var(--secondary-text-color)"}">
          ${s?"●":"○"}
        </span>
      </div>
    `}_renderEditMode(){var A,M,F,ce,C;const e=Ct(this.area.area_id,(A=this.hass)==null?void 0:A.entities,(M=this.hass)==null?void 0:M.devices),t=e.filter(v=>v.entity_id.startsWith("climate.")),i=(F=this.hass)!=null&&F.states?e.filter(v=>{var w,j;return v.entity_id.startsWith("sensor.")&&((j=(w=this.hass.states[v.entity_id])==null?void 0:w.attributes)==null?void 0:j.device_class)==="temperature"}):[],s=(ce=this.hass)!=null&&ce.states?e.filter(v=>{var w,j;return v.entity_id.startsWith("sensor.")&&((j=(w=this.hass.states[v.entity_id])==null?void 0:w.attributes)==null?void 0:j.device_class)==="humidity"}):[],o=(C=this.hass)!=null&&C.states?e.filter(v=>{var w,j;return v.entity_id.startsWith("binary_sensor.")&&["window","door","opening"].includes((j=(w=this.hass.states[v.entity_id])==null?void 0:w.attributes)==null?void 0:j.device_class)}):[],n=new Set(t.map(v=>v.entity_id)),d=[...new Set([...this.selectedThermostats,...this.selectedAcs])].filter(v=>!n.has(v)),c=new Set(i.map(v=>v.entity_id)),u=this.selectedTempSensor&&!c.has(this.selectedTempSensor)?this.selectedTempSensor:null,_=new Set(s.map(v=>v.entity_id)),g=this.selectedHumiditySensor&&!_.has(this.selectedHumiditySensor)?this.selectedHumiditySensor:null,y=new Set(o.map(v=>v.entity_id)),S=[...this.selectedWindowSensors].filter(v=>!y.has(v));return l`
      <div class="device-group">
        <div class="section-subtitle">${r("devices.climate_entities",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${t.length>0?t.map(v=>this._renderClimateRow(v.entity_id,!1)):l`<div class="no-devices">
                ${r("devices.no_climate",this.hass.language)}
              </div>`}
          ${d.map(v=>this._renderClimateRow(v,!0))}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${r("devices.temp_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${i.length>0?i.map(v=>this._renderSensorRow(v.entity_id,"temp",!1)):l`<div class="no-devices">
                ${r("devices.no_temp_sensors",this.hass.language)}
              </div>`}
          ${u?this._renderSensorRow(u,"temp",!0):p}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${r("devices.humidity_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${s.length>0?s.map(v=>this._renderSensorRow(v.entity_id,"humidity",!1)):l`<div class="no-devices">
                ${r("devices.no_humidity_sensors",this.hass.language)}
              </div>`}
          ${g?this._renderSensorRow(g,"humidity",!0):p}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${r("devices.window_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${o.length>0?o.map(v=>this._renderWindowRow(v.entity_id,!1)):l`<div class="no-devices">
                ${r("devices.no_window_sensors",this.hass.language)}
            </div>`}
          ${S.map(v=>this._renderWindowRow(v,!0))}
        </div>
        ${this.selectedWindowSensors.size>0?l`
          <div class="delay-fields">
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${r("devices.window_open_delay",this.hass.language)}
              .value=${String(this.windowOpenDelay)}
              @change=${this._onWindowOpenDelayChange}
            ></ha-textfield>
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${r("devices.window_close_delay",this.hass.language)}
              .value=${String(this.windowCloseDelay)}
              @change=${this._onWindowCloseDelayChange}
            ></ha-textfield>
          </div>
          ${this.heatingSystemType==="underfloor"&&this.windowOpenDelay<300?l`
            <div class="delay-hint">
              <ha-icon icon="mdi:information-outline"></ha-icon>
              ${r("devices.underfloor_delay_hint",this.hass.language)}
            </div>
          `:p}
        `:p}
      </div>

      <div class="entity-picker-wrap">
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["climate","sensor","binary_sensor","input_number"]}
          .entityFilter=${this._entityFilter}
          .value=${""}
          label=${r("devices.add_entity",this.hass.language)}
          @value-changed=${this._onEntityPicked}
        ></ha-entity-picker>
      </div>

      ${this.selectedThermostats.size>0?l`
        <div class="device-group">
          <div class="subtitle-row">
            <div class="section-subtitle">${r("devices.heating_system_type",this.hass.language)}</div>
            <ha-icon
              class="info-icon ${this._systemTypeInfoExpanded?"info-active":""}"
              icon="mdi:information-outline"
              @click=${()=>{this._systemTypeInfoExpanded=!this._systemTypeInfoExpanded}}
            ></ha-icon>
          </div>
          ${this._systemTypeInfoExpanded?l`
            <div class="system-type-info">${r("devices.heating_system_type_info",this.hass.language)}</div>
          `:p}
          <ha-select
            .value=${this.heatingSystemType||"standard"}
            .options=${[{value:"standard",label:r("devices.system_type_none",this.hass.language)},{value:"radiator",label:r("devices.system_type_radiator",this.hass.language)},{value:"underfloor",label:r("devices.system_type_underfloor",this.hass.language)}]}
            @selected=${this._onHeatingSystemTypeChange}
            @closed=${v=>v.stopPropagation()}
            fixedMenuPosition
            style="width: 100%;"
          >
            <ha-list-item value="standard">${r("devices.system_type_none",this.hass.language)}</ha-list-item>
            <ha-list-item value="radiator">${r("devices.system_type_radiator",this.hass.language)}</ha-list-item>
            <ha-list-item value="underfloor">${r("devices.system_type_underfloor",this.hass.language)}</ha-list-item>
          </ha-select>
        </div>
      `:p}

    `}_renderClimateRow(e,t){var u,_;const i=this.selectedThermostats.has(e),s=this.selectedAcs.has(e),o=i||s,n=this.hass.states[e],a=((u=n==null?void 0:n.attributes)==null?void 0:u.friendly_name)||e,d=n==null?void 0:n.state,c=(_=n==null?void 0:n.attributes)==null?void 0:_.current_temperature;return l`
      <div class="device-row ${o?"selected":""}">
        <ha-checkbox
          .checked=${o}
          @change=${g=>{const y=g.target;this._onClimateToggle(e,y.checked)}}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${a}</span>
            ${t?l`<span class="external-badge">${r("devices.other_area",this.hass.language)}</span>`:p}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        ${c!=null?l`<span class="device-value"
              >${c.toFixed(1)}\u00B0</span
            >`:d&&d!=="unavailable"?l`<span
                class="device-value"
                style="font-size:12px; opacity:0.6"
                >${d}</span
              >`:p}
        ${o?l`
              <ha-select
                class="device-type-select"
                outlined
                .value=${s?"ac":"thermostat"}
                .options=${[{value:"thermostat",label:r("devices.type_thermostat",this.hass.language)},{value:"ac",label:r("devices.type_ac",this.hass.language)}]}
                @selected=${g=>{this._onDeviceTypeChange(e,pe(g))}}
                @closed=${g=>g.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="thermostat">${r("devices.type_thermostat",this.hass.language)}</ha-list-item>
                <ha-list-item value="ac">${r("devices.type_ac",this.hass.language)}</ha-list-item>
              </ha-select>
            `:p}
      </div>
    `}_renderSensorRow(e,t,i){var _;const s=this.hass.states[e],o=((_=s==null?void 0:s.attributes)==null?void 0:_.friendly_name)||e,n=s==null?void 0:s.state,d=(t==="temp"?this.selectedTempSensor:this.selectedHumiditySensor)===e,c=t==="temp"?f(this.hass):"%",u=n&&n!=="unknown"&&n!=="unavailable";return l`
      <div class="device-row ${d?"selected":""}"
        @click=${()=>this._onSensorSelected(d?"":e,t)}
      >
        <ha-radio
          .checked=${d}
          name="${t}-sensor"
        ></ha-radio>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${o}</span>
            ${i?l`<span class="external-badge">${r("devices.other_area",this.hass.language)}</span>`:p}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        ${u?l`<span class="device-value">${t==="humidity"?Math.round(Number(n)):n}${c}</span>`:p}
      </div>
    `}_renderWindowRow(e,t){var a;const i=this.selectedWindowSensors.has(e),s=this.hass.states[e],o=((a=s==null?void 0:s.attributes)==null?void 0:a.friendly_name)||e,n=(s==null?void 0:s.state)==="on";return l`
      <div class="device-row ${i?"selected":""}">
        <ha-checkbox
          .checked=${i}
          @change=${d=>{const c=d.target;this._onWindowSensorToggle(e,c.checked)}}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${o}</span>
            ${t?l`<span class="external-badge">${r("devices.other_area",this.hass.language)}</span>`:p}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        <span class="device-value" style="color: ${n?"var(--warning-color, #ff9800)":"var(--secondary-text-color)"}">
          ${n?"●":"○"}
        </span>
      </div>
    `}_detectClimateType(e){var s,o;const t=(o=(s=this.hass.states[e])==null?void 0:s.attributes)==null?void 0:o.hvac_modes;return t&&(t.includes("cool")||t.includes("heat_cool"))?"ac":"thermostat"}_onClimateToggle(e,t){this.dispatchEvent(new CustomEvent("climate-toggle",{detail:{entityId:e,checked:t,detectedType:this._detectClimateType(e)},bubbles:!0,composed:!0}))}_onDeviceTypeChange(e,t){this.dispatchEvent(new CustomEvent("device-type-change",{detail:{entityId:e,type:t},bubbles:!0,composed:!0}))}_onSensorSelected(e,t){this.dispatchEvent(new CustomEvent("sensor-selected",{detail:{entityId:e,type:t},bubbles:!0,composed:!0}))}_onWindowSensorToggle(e,t){this.dispatchEvent(new CustomEvent("window-sensor-toggle",{detail:{entityId:e,checked:t},bubbles:!0,composed:!0}))}_onWindowOpenDelayChange(e){const t=Math.max(0,parseInt(e.target.value)||0);this.dispatchEvent(new CustomEvent("window-open-delay-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onWindowCloseDelayChange(e){const t=Math.max(0,parseInt(e.target.value)||0);this.dispatchEvent(new CustomEvent("window-close-delay-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onHeatingSystemTypeChange(e){const t=pe(e)??"",i=t==="standard"?"":t;this.dispatchEvent(new CustomEvent("heating-system-type-changed",{detail:{value:i},bubbles:!0,composed:!0}))}_onEntityPicked(e){var n,a,d,c,u;const t=(n=e.detail)==null?void 0:n.value;if(!t)return;let i;t.startsWith("climate.")?i="climate":t.startsWith("binary_sensor.")?i="window":t.startsWith("input_number.")?i=((d=(a=this.hass.states[t])==null?void 0:a.attributes)==null?void 0:d.unit_of_measurement)==="%"?"humidity":"temp":i=((u=(c=this.hass.states[t])==null?void 0:c.attributes)==null?void 0:u.device_class)==="humidity"?"humidity":"temp";const s=i==="climate"?this._detectClimateType(t):void 0;this.dispatchEvent(new CustomEvent("external-entity-added",{detail:{entityId:t,category:i,detectedType:s},bubbles:!0,composed:!0}));const o=e.target;o.value=""}};U.styles=D`
    :host {
      display: block;
    }

    .section-subtitle {
      font-size: 12px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin: 12px 0 8px 0;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    .section-subtitle:first-child {
      margin-top: 0;
    }

    .device-group {
      padding: 4px 0;
    }

    .device-group + .device-group {
      margin-top: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .device-list-scroll {
      max-height: 168px;
      overflow-y: auto;
      overflow-x: hidden;
      scrollbar-width: thin;
    }

    /* Device rows */
    .device-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 14px;
      font-size: 14px;
      color: var(--primary-text-color);
      border-radius: 10px;
      margin-bottom: 2px;
      transition: background 0.15s;
    }

    .device-row:last-child {
      margin-bottom: 0;
    }

    .device-row:hover {
      background: rgba(0, 0, 0, 0.02);
    }

    .device-row.selected {
      background: rgba(3, 169, 244, 0.035);
    }

    .device-row ha-checkbox,
    .device-row ha-radio {
      flex-shrink: 0;
    }

    .device-info {
      flex: 1;
      min-width: 0;
    }

    .device-name-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .device-name {
      font-size: 14px;
      font-weight: 450;
      color: var(--primary-text-color);
    }

    .device-value {
      margin-left: auto;
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
      flex-shrink: 0;
    }

    .device-entity {
      font-family: var(--code-font-family, monospace);
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 2px;
      opacity: 0.7;
    }

    .external-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 10px;
      font-weight: 500;
      color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.1);
      padding: 2px 8px;
      border-radius: 10px;
      letter-spacing: 0.3px;
      text-transform: uppercase;
      flex-shrink: 0;
    }

    .device-type-select {
      flex-shrink: 0;
      --ha-select-min-width: 90px;
    }

    .no-devices {
      color: var(--secondary-text-color);
      font-size: 13px;
      font-style: italic;
      padding: 12px 14px;
    }

    .entity-picker-wrap {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .subtitle-row {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .info-icon {
      --mdc-icon-size: 16px;
      color: var(--secondary-text-color);
      cursor: pointer;
      opacity: 0.6;
    }
    .info-icon:hover, .info-icon.info-active {
      opacity: 1;
      color: var(--primary-color);
    }

    .system-type-info {
      font-size: 12px;
      line-height: 1.5;
      color: var(--secondary-text-color);
      padding: 8px 14px 4px;
    }

    ha-entity-picker {
      width: 100%;
    }

    /* View mode styles */
    .view-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .view-name {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .entity-link {
      cursor: pointer;
    }

    .entity-link:hover {
      text-decoration: underline;
    }

    .view-value {
      font-weight: 500;
      flex-shrink: 0;
    }

    .delay-fields {
      display: flex;
      gap: 12px;
      margin-top: 8px;
      padding: 0 14px;
    }

    .delay-fields ha-textfield {
      flex: 1;
    }

    .delay-view {
      font-size: 12px;
      color: var(--secondary-text-color);
      padding: 4px 14px 0;
    }

    .delay-hint {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      font-size: 12px;
      line-height: 1.5;
      color: var(--warning-color, #ff9800);
      padding: 8px 14px 0;
    }

    .delay-hint ha-icon {
      --mdc-icon-size: 16px;
      flex-shrink: 0;
      margin-top: 1px;
    }
  `,G([h({attribute:!1})],U.prototype,"hass",2),G([h({attribute:!1})],U.prototype,"area",2),G([h({attribute:!1})],U.prototype,"selectedThermostats",2),G([h({attribute:!1})],U.prototype,"selectedAcs",2),G([h({type:String})],U.prototype,"selectedTempSensor",2),G([h({type:String})],U.prototype,"selectedHumiditySensor",2),G([h({attribute:!1})],U.prototype,"selectedWindowSensors",2),G([h({type:Number})],U.prototype,"windowOpenDelay",2),G([h({type:Number})],U.prototype,"windowCloseDelay",2),G([h({type:String})],U.prototype,"heatingSystemType",2),G([h({type:Boolean})],U.prototype,"editing",2),G([m()],U.prototype,"_systemTypeInfoExpanded",2),U=G([R("rs-device-section")],U);const lt=D`
  .info-icon {
    --mdc-icon-size: 16px;
    color: var(--secondary-text-color);
    opacity: 0.3;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s, color 0.15s;
  }

  .info-icon:hover {
    opacity: 0.7;
  }

  .info-icon.info-active {
    opacity: 1;
    color: var(--primary-color);
  }

  .info-panel {
    padding: 12px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
    font-size: 13px;
    line-height: 1.6;
    color: var(--secondary-text-color);
  }

  .info-panel strong {
    display: block;
    margin-bottom: 4px;
    color: var(--primary-text-color);
    font-size: 13px;
  }
`;var Ci=Object.defineProperty,ki=Object.getOwnPropertyDescriptor,be=(e,t,i,s)=>{for(var o=s>1?void 0:s?ki(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Ci(t,i,o),o};const Ei="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",Ai="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";let le=class extends z{constructor(){super(...arguments),this.icon="",this.heading="",this.editable=!1,this.editing=!1,this.doneLabel="",this.hasInfo=!1,this._infoExpanded=!1}render(){return l`
      <ha-card>
        <div class="section-header">
          <ha-icon class="section-icon" icon=${this.icon}></ha-icon>
          <h3 class="section-title">${this.heading}</h3>
          ${this.hasInfo?l`
                <ha-icon
                  class="info-icon ${this._infoExpanded?"info-active":""}"
                  icon="mdi:information-outline"
                  @click=${this._toggleInfo}
                ></ha-icon>
              `:p}
          ${this.editable&&!this.editing?l`
                <ha-icon-button
                  class="edit-btn"
                  .path=${Ei}
                  @click=${this._onEditClick}
                ></ha-icon-button>
              `:p}
          ${this.editable&&this.editing?l`
                <button class="done-btn" @click=${this._onDoneClick}>
                  <ha-icon-button
                    style="--mdc-icon-button-size: 20px; --mdc-icon-size: 14px; pointer-events: none;"
                    .path=${Ai}
                  ></ha-icon-button>
                  ${this.doneLabel}
                </button>
              `:p}
        </div>
        ${this._infoExpanded?l`<div class="section-info"><div class="info-panel"><slot name="info"></slot></div></div>`:p}
        <div class="section-body">
          <slot></slot>
        </div>
      </ha-card>
    `}_toggleInfo(){this._infoExpanded=!this._infoExpanded}_onEditClick(){this.dispatchEvent(new CustomEvent("edit-click",{bubbles:!0,composed:!0}))}_onDoneClick(){this.dispatchEvent(new CustomEvent("done-click",{bubbles:!0,composed:!0}))}};le.styles=[lt,D`
      :host {
        display: block;
      }

      ha-card {
        overflow: hidden;
        min-width: 0;
      }

      .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 16px 20px 12px;
      }

      .section-icon {
        --mdc-icon-size: 18px;
        opacity: 0.7;
      }

      .section-title {
        font-size: 15px;
        font-weight: 500;
        color: var(--primary-text-color);
        margin: 0;
        flex: 1;
      }

      .edit-btn {
        --mdc-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        margin: -4px -8px -4px 0;
      }

      .done-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        background: none;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 16px;
        color: var(--primary-color);
        font-size: 12px;
        font-weight: 500;
        padding: 4px 12px 4px 8px;
        cursor: pointer;
        transition: background 0.15s;
        --mdc-icon-size: 14px;
      }

      .done-btn:hover {
        background: rgba(3, 169, 244, 0.05);
      }

      .section-info {
        padding: 0 20px 8px;
      }

      .section-body {
        padding: 0 20px 20px;
      }
    `],be([h({type:String})],le.prototype,"icon",2),be([h({type:String})],le.prototype,"heading",2),be([h({type:Boolean})],le.prototype,"editable",2),be([h({type:Boolean})],le.prototype,"editing",2),be([h({type:String})],le.prototype,"doneLabel",2),be([h({type:Boolean})],le.prototype,"hasInfo",2),be([m()],le.prototype,"_infoExpanded",2),le=be([R("rs-section-card")],le);var Ti=Object.defineProperty,Mi=Object.getOwnPropertyDescriptor,B=(e,t,i,s)=>{for(var o=s>1?void 0:s?Mi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Ti(t,i,o),o};let I=class extends z{constructor(){super(...arguments),this.climateMode="auto",this.comfortHeat=21,this.comfortCool=24,this.ecoHeat=17,this.ecoCool=27,this.language="en",this._overridePending=null,this._overrideCustomTemp=21,this._overrideError="",this._optimisticOverride=null,this._optimisticClear=!1}updated(e){var t;if(e.has("config")&&((t=this.config)!=null&&t.live)){const i=this.config.live;this._optimisticOverride&&i.override_active&&(this._optimisticOverride=null),this._optimisticClear&&!i.override_active&&(this._optimisticClear=!1)}}getEffectiveOverride(){var t;if(this._optimisticClear)return{active:!1,type:null,temp:null,until:null};if(this._optimisticOverride)return{active:!0,type:this._optimisticOverride.type,temp:this._optimisticOverride.temp,until:this._optimisticOverride.until};const e=(t=this.config)==null?void 0:t.live;return e!=null&&e.override_active&&e.override_type?{active:!0,type:e.override_type,temp:e.override_temp,until:e.override_until}:{active:!1,type:null,temp:null,until:null}}render(){const e=this.getEffectiveOverride();return l`
      <hr class="override-divider" />
      <div class="override-label">${r("override.label",this.language)}</div>
      ${this._renderOverrideButtons(e)}
      ${this._overrideError?l`<div class="override-error">${this._overrideError}</div>`:p}
    `}_renderOverrideButtons(e){const t=e.active?e.type:null,i=!t&&this._overridePending;return l`
      <div class="override-presets">
        ${["boost","eco","custom"].map(s=>{const o=t===s,n=t!==null&&!o,a=!t&&this._overridePending===s;return l`
            <button
              class="override-preset ${s} ${o?"active":""} ${a?"pending":""}"
              ?disabled=${n}
              @click=${()=>o?this._onClearOverride():this._onOverridePreset(s)}
            >
              <ha-icon icon=${s==="boost"?"mdi:fire":s==="eco"?"mdi:leaf":"mdi:thermometer"}></ha-icon>
              ${s==="boost"?`${r("override.comfort",this.language)} ${P(this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat,this.hass)}${f(this.hass)}`:s==="eco"?`${r("override.eco",this.language)} ${P(this.climateMode==="cool_only"?this.ecoCool:this.ecoHeat,this.hass)}${f(this.hass)}`:r("override.custom",this.language)}
            </button>
          `})}
      </div>
      ${i?l`
            ${this._overridePending==="custom"?l`
                  <div class="override-custom-row">
                    <span>${r("override.target",this.language)}</span>
                    <input
                      type="number"
                      min=${H(5,35,this.hass).min}
                      max=${H(5,35,this.hass).max}
                      step=${re(this.hass)}
                      .value=${String(O(this._overrideCustomTemp,this.hass))}
                      @input=${this._onOverrideCustomTempInput}
                    />
                    <span>${f(this.hass)}</span>
                  </div>
                `:p}
            <div class="override-duration">
              <span class="override-duration-label">${r("override.activate_for",this.language)}</span>
              ${[{label:"1h",hours:1},{label:"2h",hours:2},{label:"4h",hours:4}].map(s=>l`
                  <button
                    class="override-dur-chip"
                    @click=${()=>this._onOverrideActivate(s.hours)}
                  >
                    ${s.label}
                  </button>
                `)}
            </div>
          `:p}
    `}_onOverridePreset(e){this._overridePending===e?this._overridePending=null:(this._overridePending=e,e==="custom"&&(this._overrideCustomTemp=this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat)),this._overrideError=""}_onOverrideCustomTempInput(e){this._overrideCustomTemp=ye(Number(e.target.value)||O(21,this.hass),this.hass)}async _onOverrideActivate(e){if(!this._overridePending||!this.config)return;const t=this._overridePending;let i;t==="boost"?i=this.climateMode==="cool_only"?this.comfortCool:this.comfortHeat:t==="eco"?i=this.climateMode==="cool_only"?this.ecoCool:this.ecoHeat:i=this._overrideCustomTemp,this._optimisticOverride={type:t,temp:i,until:Date.now()/1e3+e*3600},this._optimisticClear=!1,this._overridePending=null,this._overrideError="";const s={type:"roommind/override/set",area_id:this.config.area_id,override_type:t,duration:e};t==="custom"&&(s.temperature=i);try{await this.hass.callWS(s),this._fireRoomUpdated()}catch(o){this._optimisticOverride=null,this._overrideError=o instanceof Error?o.message:r("override.error_set",this.language),console.error("Override set failed:",o)}}async _onClearOverride(){if(this.config){this._optimisticClear=!0,this._optimisticOverride=null,this._overrideError="";try{await this.hass.callWS({type:"roommind/override/clear",area_id:this.config.area_id}),this._fireRoomUpdated()}catch(e){this._optimisticClear=!1,this._overrideError=e instanceof Error?e.message:r("override.error_clear",this.language),console.error("Override clear failed:",e)}}}_fireRoomUpdated(){this.dispatchEvent(new CustomEvent("room-updated",{bubbles:!0,composed:!0}))}};I.styles=D`
    :host {
      display: block;
    }

    .override-divider {
      border: none;
      border-top: 1px solid var(--divider-color, #e0e0e0);
      margin: 16px 0 12px;
    }

    .override-label {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 10px;
    }

    .override-presets {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .override-preset {
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 13px;
      background: transparent;
      color: var(--primary-text-color);
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s, border-color 0.15s;
    }

    .override-preset:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .override-preset.pending {
      border-color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .override-preset.active.boost {
      border-color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.15);
      color: var(--warning-color, #ff9800);
    }

    .override-preset.active.eco {
      border-color: #4caf50;
      background: rgba(76, 175, 80, 0.15);
      color: #4caf50;
    }

    .override-preset.active.custom {
      border-color: #2196f3;
      background: rgba(33, 150, 243, 0.15);
      color: #2196f3;
    }

    .override-preset:disabled {
      opacity: 0.35;
      cursor: default;
    }

    .override-preset:disabled:hover {
      background: transparent;
    }

    .override-preset ha-icon {
      --mdc-icon-size: 16px;
    }

    .override-duration {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      align-items: center;
    }

    .override-duration-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-dur-chip {
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 12px;
      background: transparent;
      color: var(--primary-text-color);
      transition: background 0.15s;
    }

    .override-dur-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .override-dur-chip:disabled {
      opacity: 0.5;
      pointer-events: none;
    }

    .override-custom-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }

    .override-custom-row input {
      width: 56px;
      padding: 4px 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
      font-size: 13px;
      text-align: center;
      background: transparent;
      color: var(--primary-text-color);
    }

    .override-custom-row span {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-error {
      color: var(--error-color, #d32f2f);
      font-size: 12px;
      margin-top: 6px;
    }
  `,B([h({attribute:!1})],I.prototype,"hass",2),B([h({attribute:!1})],I.prototype,"config",2),B([h()],I.prototype,"climateMode",2),B([h({type:Number})],I.prototype,"comfortHeat",2),B([h({type:Number})],I.prototype,"comfortCool",2),B([h({type:Number})],I.prototype,"ecoHeat",2),B([h({type:Number})],I.prototype,"ecoCool",2),B([h()],I.prototype,"language",2),B([m()],I.prototype,"_overridePending",2),B([m()],I.prototype,"_overrideCustomTemp",2),B([m()],I.prototype,"_overrideError",2),B([m()],I.prototype,"_optimisticOverride",2),B([m()],I.prototype,"_optimisticClear",2),I=B([R("rs-override-section")],I);var zi=Object.defineProperty,Pi=Object.getOwnPropertyDescriptor,ke=(e,t,i,s)=>{for(var o=s>1?void 0:s?Pi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&zi(t,i,o),o};let ue=class extends z{constructor(){super(...arguments),this.presenceEnabled=!1,this.presencePersons=[],this.selectedPresencePersons=[],this.editing=!1,this.language="en"}render(){return!this.presenceEnabled||this.presencePersons.length===0?p:l`
      <rs-section-card
        icon="mdi:home-account"
        .heading=${r("room.section.presence",this.language)}
        editable
        .editing=${this.editing}
        .doneLabel=${r("schedule.done",this.language)}
        @edit-click=${this._onEditClick}
        @done-click=${this._onDoneClick}
      >
        ${this.editing?this._renderEditMode():this._renderViewMode()}
      </rs-section-card>
    `}_renderEditMode(){return l`
      <div style="padding: 0 16px 16px">
        <div class="presence-chips">
          ${this.presencePersons.map(e=>{var s,o;const t=this.selectedPresencePersons.includes(e),i=((o=(s=this.hass.states[e])==null?void 0:s.attributes)==null?void 0:o.friendly_name)??e.split(".").slice(1).join(".");return l`
              <button
                class="presence-chip ${t?"active":""}"
                @click=${()=>this._onTogglePerson(e,t)}
              >
                <ha-icon icon=${t?"mdi:account-check":"mdi:account-outline"} style="--mdc-icon-size: 16px"></ha-icon>
                ${i}
              </button>
            `})}
        </div>
        <ha-expansion-panel outlined .header=${r("presence.room_help_header",this.language)} style="margin-top: 12px">
          <div class="help-content">
            <p>${r("presence.room_help_body",this.language)}</p>
          </div>
        </ha-expansion-panel>
      </div>
    `}_renderViewMode(){return l`
      <div style="padding: 0 16px 16px">
        ${this.selectedPresencePersons.length>0?l`
          <div class="presence-list">
            ${this.selectedPresencePersons.map(e=>{var o,n,a;const t=((n=(o=this.hass.states[e])==null?void 0:o.attributes)==null?void 0:n.friendly_name)??e.split(".").slice(1).join("."),i=(a=this.hass.states[e])==null?void 0:a.state,s=e.startsWith("person.")||e.startsWith("device_tracker.")?i==="home":i==="on";return l`
                <div class="presence-row ${s?"home":"away"}">
                  <span class="presence-dot"></span>
                  <span class="presence-name">${t}</span>
                  <span class="presence-state">${s?r("presence.state_home",this.language):r("presence.state_away",this.language)}</span>
                </div>
              `})}
          </div>
        `:l`
          <span class="field-hint">${r("presence.room_none_assigned",this.language)}</span>
        `}
      </div>
    `}_onEditClick(){this.editing=!0,this.dispatchEvent(new CustomEvent("editing-changed",{detail:{editing:!0},bubbles:!0,composed:!0}))}_onDoneClick(){this.editing=!1,this.dispatchEvent(new CustomEvent("editing-changed",{detail:{editing:!1},bubbles:!0,composed:!0}))}_onTogglePerson(e,t){let i;t?i=this.selectedPresencePersons.filter(s=>s!==e):i=[...this.selectedPresencePersons,e],this.dispatchEvent(new CustomEvent("presence-persons-changed",{detail:i,bubbles:!0,composed:!0}))}};ue.styles=D`
    :host {
      display: block;
    }

    .presence-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .presence-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 13px;
      font-family: inherit;
      background: transparent;
      color: var(--secondary-text-color);
      transition: background 0.15s, border-color 0.15s, color 0.15s;
    }

    .presence-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-chip.active {
      border-color: var(--primary-color);
      color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .presence-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s;
    }

    .presence-row.home {
      background: rgba(76, 175, 80, 0.1);
    }

    .presence-row.away {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .presence-row.home .presence-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .presence-row.away .presence-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .presence-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .presence-row.home .presence-name {
      color: var(--primary-text-color);
    }

    .presence-row.away .presence-name {
      color: var(--secondary-text-color);
    }

    .presence-state {
      font-size: 12px;
      white-space: nowrap;
    }

    .presence-row.home .presence-state {
      color: #2e7d32;
    }

    .presence-row.away .presence-state {
      color: var(--secondary-text-color);
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .help-content {
      padding: 0 16px 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }
  `,ke([h({attribute:!1})],ue.prototype,"hass",2),ke([h({type:Boolean})],ue.prototype,"presenceEnabled",2),ke([h({attribute:!1})],ue.prototype,"presencePersons",2),ke([h({attribute:!1})],ue.prototype,"selectedPresencePersons",2),ke([h({type:Boolean})],ue.prototype,"editing",2),ke([h()],ue.prototype,"language",2),ue=ke([R("rs-presence-section")],ue);var Di=Object.defineProperty,Ri=Object.getOwnPropertyDescriptor,k=(e,t,i,s)=>{for(var o=s>1?void 0:s?Ri(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Di(t,i,o),o};let $=class extends z{constructor(){super(...arguments),this.config=null,this.presenceEnabled=!1,this.presencePersons=[],this.climateControlActive=!0,this._selectedThermostats=new Set,this._selectedAcs=new Set,this._selectedTempSensor="",this._selectedHumiditySensor="",this._selectedWindowSensors=new Set,this._windowOpenDelay=0,this._windowCloseDelay=0,this._climateMode="auto",this._schedules=[],this._scheduleSelectorEntity="",this._comfortHeat=21,this._comfortCool=24,this._ecoHeat=17,this._ecoCool=27,this._error="",this._dirty=!1,this._editingSchedule=!1,this._editingDevices=!1,this._editingPresence=!1,this._selectedPresencePersons=[],this._displayName="",this._heatingSystemType="",this._prevAreaId=null}connectedCallback(){super.connectedCallback(),this._initFromConfig()}disconnectedCallback(){super.disconnectedCallback(),this._saveDebounce&&clearTimeout(this._saveDebounce)}updated(e){var s,o;const t=((s=this.config)==null?void 0:s.area_id)??((o=this.area)==null?void 0:o.area_id)??null;if(t!==this._prevAreaId)this._initFromConfig(),this._prevAreaId=t;else if(e.has("config")&&!this._dirty){const n=e.get("config");n==null&&this._initFromConfig()}}_initFromConfig(){this.config?(this._selectedThermostats=new Set(this.config.thermostats),this._selectedAcs=new Set(this.config.acs),this._selectedTempSensor=this.config.temperature_sensor,this._selectedHumiditySensor=this.config.humidity_sensor??"",this._selectedWindowSensors=new Set(this.config.window_sensors??[]),this._windowOpenDelay=this.config.window_open_delay??0,this._windowCloseDelay=this.config.window_close_delay??0,this._climateMode=this.config.climate_mode,this._schedules=this.config.schedules??[],this._scheduleSelectorEntity=this.config.schedule_selector_entity??"",this._comfortHeat=this.config.comfort_heat??this.config.comfort_temp??21,this._comfortCool=this.config.comfort_cool??24,this._ecoHeat=this.config.eco_heat??this.config.eco_temp??17,this._ecoCool=this.config.eco_cool??27,this._selectedPresencePersons=this.config.presence_persons??[],this._displayName=this.config.display_name??"",this._heatingSystemType=this.config.heating_system_type??""):(this._selectedThermostats=new Set,this._selectedAcs=new Set,this._selectedTempSensor="",this._selectedHumiditySensor="",this._selectedWindowSensors=new Set,this._windowOpenDelay=0,this._windowCloseDelay=0,this._climateMode="auto",this._schedules=[],this._scheduleSelectorEntity="",this._comfortHeat=21,this._comfortCool=24,this._ecoHeat=17,this._ecoCool=27,this._selectedPresencePersons=[],this._displayName="",this._heatingSystemType=""),this._dirty=!1;const e=this._selectedThermostats.size>0||this._selectedAcs.size>0||!!this._selectedTempSensor;this._editingSchedule=this._schedules.length===0,this._editingDevices=!e}_getEffectiveOverride(){var i,s;const e=(i=this.shadowRoot)==null?void 0:i.querySelector("rs-override-section");if(e)return e.getEffectiveOverride();const t=(s=this.config)==null?void 0:s.live;return t!=null&&t.override_active&&t.override_type?{active:!0,type:t.override_type,temp:t.override_temp,until:t.override_until}:{active:!1,type:null,temp:null,until:null}}render(){var e,t;return this.area?l`
      <div class="detail-layout">
        <div class="col-left">
          <rs-hero-status
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .overrideInfo=${this._getEffectiveOverride()}
            .climateControlActive=${this.climateControlActive}
            @display-name-changed=${this._onDisplayNameChanged}
          ></rs-hero-status>

          <rs-section-card
            icon="mdi:cog"
            .heading=${r("room.section.climate_mode",this.hass.language)}
            hasInfo
          >
            <div slot="info">
              <b>${r("mode.auto",this.hass.language)}</b> — ${r("mode.auto_desc",this.hass.language)}<br>
              <b>${r("mode.heat_only",this.hass.language)}</b> — ${r("mode.heat_only_desc",this.hass.language)}<br>
              <b>${r("mode.cool_only",this.hass.language)}</b> — ${r("mode.cool_only_desc",this.hass.language)}
            </div>
            <rs-climate-mode-selector
              .climateMode=${this._climateMode}
              .language=${this.hass.language}
              @mode-changed=${this._onModeChanged}
            ></rs-climate-mode-selector>
          </rs-section-card>

          <rs-section-card
            icon="mdi:calendar"
            .heading=${r("room.section.schedule",this.hass.language)}
            editable
            .editing=${this._editingSchedule}
            .doneLabel=${r("schedule.done",this.hass.language)}
            @edit-click=${()=>{this._editingSchedule=!0}}
            @done-click=${()=>{this._editingSchedule=!1}}
          >
            <rs-schedule-settings
              .hass=${this.hass}
              .schedules=${this._schedules}
              .scheduleSelectorEntity=${this._scheduleSelectorEntity}
              .activeScheduleIndex=${((t=(e=this.config)==null?void 0:e.live)==null?void 0:t.active_schedule_index)??-1}
              .comfortHeat=${this._comfortHeat}
              .comfortCool=${this._comfortCool}
              .ecoHeat=${this._ecoHeat}
              .ecoCool=${this._ecoCool}
              .climateMode=${this._climateMode}
              .editing=${this._editingSchedule}
              @schedules-changed=${this._onSchedulesChanged}
              @schedule-selector-changed=${this._onScheduleSelectorChanged}
              @comfort-heat-changed=${this._onComfortHeatChanged}
              @comfort-cool-changed=${this._onComfortCoolChanged}
              @eco-heat-changed=${this._onEcoHeatChanged}
              @eco-cool-changed=${this._onEcoCoolChanged}
            ></rs-schedule-settings>
            ${this.config?l`
              <rs-override-section
                .hass=${this.hass}
                .config=${this.config}
                .climateMode=${this._climateMode}
                .comfortHeat=${this._comfortHeat}
                .comfortCool=${this._comfortCool}
                .ecoHeat=${this._ecoHeat}
                .ecoCool=${this._ecoCool}
                .language=${this.hass.language}
              ></rs-override-section>
            `:p}
          </rs-section-card>

          ${this._error?l`<div class="error">${this._error}</div>`:p}
        </div>

        <div class="col-right">
          <rs-section-card
            icon="mdi:power-plug"
            .heading=${r("room.section.devices",this.hass.language)}
            editable
            .editing=${this._editingDevices}
            .doneLabel=${r("devices.done",this.hass.language)}
            @edit-click=${()=>{this._editingDevices=!0}}
            @done-click=${()=>{this._editingDevices=!1}}
          >
            <rs-device-section
              .hass=${this.hass}
              .area=${this.area}
              .editing=${this._editingDevices}
              .selectedThermostats=${this._selectedThermostats}
              .selectedAcs=${this._selectedAcs}
              .selectedTempSensor=${this._selectedTempSensor}
              .selectedHumiditySensor=${this._selectedHumiditySensor}
              .selectedWindowSensors=${this._selectedWindowSensors}
              .windowOpenDelay=${this._windowOpenDelay}
              .windowCloseDelay=${this._windowCloseDelay}
              .heatingSystemType=${this._heatingSystemType}
              @climate-toggle=${this._onClimateToggle}
              @device-type-change=${this._onDeviceTypeChange}
              @sensor-selected=${this._onSensorSelected}
              @window-sensor-toggle=${this._onWindowSensorToggle}
              @window-open-delay-changed=${this._onWindowOpenDelayChanged}
              @window-close-delay-changed=${this._onWindowCloseDelayChanged}
              @external-entity-added=${this._onExternalEntityAdded}
              @heating-system-type-changed=${this._onHeatingSystemTypeChanged}
            ></rs-device-section>
          </rs-section-card>

          <rs-presence-section
            .hass=${this.hass}
            .presenceEnabled=${this.presenceEnabled}
            .presencePersons=${this.presencePersons}
            .selectedPresencePersons=${this._selectedPresencePersons}
            .editing=${this._editingPresence}
            .language=${this.hass.language}
            @presence-persons-changed=${this._onPresencePersonsChanged}
            @editing-changed=${this._onPresenceEditingChanged}
          ></rs-presence-section>
        </div>
      </div>
    `:p}_onModeChanged(e){this._climateMode=e.detail.mode,this._autoSave()}_onSchedulesChanged(e){this._schedules=e.detail.value,this._autoSave()}_onScheduleSelectorChanged(e){this._scheduleSelectorEntity=e.detail.value,this._autoSave()}_onComfortHeatChanged(e){this._comfortHeat=e.detail.value,this._comfortCool<this._comfortHeat&&(this._comfortCool=this._comfortHeat),this._autoSave()}_onComfortCoolChanged(e){this._comfortCool=e.detail.value,this._comfortHeat>this._comfortCool&&(this._comfortHeat=this._comfortCool),this._autoSave()}_onEcoHeatChanged(e){this._ecoHeat=e.detail.value,this._ecoCool<this._ecoHeat&&(this._ecoCool=this._ecoHeat),this._autoSave()}_onEcoCoolChanged(e){this._ecoCool=e.detail.value,this._ecoHeat>this._ecoCool&&(this._ecoHeat=this._ecoCool),this._autoSave()}_onClimateToggle(e){const{entityId:t,checked:i,detectedType:s}=e.detail;if(i){const o=new Set(this._selectedThermostats),n=new Set(this._selectedAcs);s==="ac"?n.add(t):o.add(t),this._selectedThermostats=o,this._selectedAcs=n}else{const o=new Set(this._selectedThermostats),n=new Set(this._selectedAcs);o.delete(t),n.delete(t),this._selectedThermostats=o,this._selectedAcs=n}this._autoSave()}_onDeviceTypeChange(e){const{entityId:t,type:i}=e.detail,s=new Set(this._selectedThermostats),o=new Set(this._selectedAcs);i==="thermostat"?(o.delete(t),s.add(t)):(s.delete(t),o.add(t)),this._selectedThermostats=s,this._selectedAcs=o,this._autoSave()}_onSensorSelected(e){e.detail.type==="temp"?this._selectedTempSensor=e.detail.entityId:this._selectedHumiditySensor=e.detail.entityId,this._autoSave()}_onWindowSensorToggle(e){const{entityId:t,checked:i}=e.detail,s=new Set(this._selectedWindowSensors);i?s.add(t):s.delete(t),this._selectedWindowSensors=s,this._autoSave()}_onWindowOpenDelayChanged(e){this._windowOpenDelay=e.detail.value,this._autoSave()}_onWindowCloseDelayChanged(e){this._windowCloseDelay=e.detail.value,this._autoSave()}_onHeatingSystemTypeChanged(e){this._heatingSystemType=e.detail.value,this._autoSave()}_onExternalEntityAdded(e){const{entityId:t,category:i,detectedType:s}=e.detail;if(i==="climate"){const o=new Set(this._selectedThermostats),n=new Set(this._selectedAcs);s==="ac"?n.add(t):o.add(t),this._selectedThermostats=o,this._selectedAcs=n}else if(i==="temp")this._selectedTempSensor=t;else if(i==="window"){const o=new Set(this._selectedWindowSensors);o.add(t),this._selectedWindowSensors=o}else this._selectedHumiditySensor=t;this._autoSave()}_onPresencePersonsChanged(e){this._selectedPresencePersons=e.detail,this._autoSave()}_onPresenceEditingChanged(e){this._editingPresence=e.detail.editing}_onDisplayNameChanged(e){this._displayName=e.detail.value,this._autoSave()}_autoSave(){this._dirty=!0,this._saveDebounce&&clearTimeout(this._saveDebounce),this._saveDebounce=setTimeout(()=>this._doSave(),500)}async _doSave(){J(this,"saving"),this._error="";try{await this.hass.callWS({type:"roommind/rooms/save",area_id:this.area.area_id,thermostats:[...this._selectedThermostats],acs:[...this._selectedAcs],temperature_sensor:this._selectedTempSensor,humidity_sensor:this._selectedHumiditySensor,window_sensors:[...this._selectedWindowSensors],window_open_delay:this._windowOpenDelay,window_close_delay:this._windowCloseDelay,climate_mode:this._climateMode,schedules:this._schedules,schedule_selector_entity:this._scheduleSelectorEntity,comfort_heat:this._comfortHeat,comfort_cool:this._comfortCool,eco_heat:this._ecoHeat,eco_cool:this._ecoCool,presence_persons:this._selectedPresencePersons.filter(e=>e),display_name:this._displayName,heating_system_type:this._heatingSystemType}),this._dirty=!1,J(this,"saved"),this.dispatchEvent(new CustomEvent("room-updated",{bubbles:!0,composed:!0}))}catch(e){const t=e instanceof Error?e.message:r("room.error_save_fallback",this.hass.language);this._error=t,J(this,"error")}}};$.styles=D`
    :host {
      display: block;
      max-width: 1100px;
      margin: 0 auto;
    }

    .detail-layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .col-left,
    .col-right {
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
    }

    @media (max-width: 860px) {
      .detail-layout {
        grid-template-columns: 1fr;
      }
    }

    /* Section cards handled by rs-section-card */

    /* Actions */
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 8px;
      margin-bottom: 24px;
    }

    .error {
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      margin-top: 8px;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .exceptions-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px 0 0;
      margin: 0;
      cursor: pointer;
      font-size: 13px;
      color: var(--primary-color);
      font-family: inherit;
    }

    .exceptions-link:hover {
      text-decoration: underline;
    }
  `,k([h({attribute:!1})],$.prototype,"area",2),k([h({attribute:!1})],$.prototype,"config",2),k([h({attribute:!1})],$.prototype,"hass",2),k([h({type:Boolean})],$.prototype,"presenceEnabled",2),k([h({attribute:!1})],$.prototype,"presencePersons",2),k([h({type:Boolean})],$.prototype,"climateControlActive",2),k([m()],$.prototype,"_selectedThermostats",2),k([m()],$.prototype,"_selectedAcs",2),k([m()],$.prototype,"_selectedTempSensor",2),k([m()],$.prototype,"_selectedHumiditySensor",2),k([m()],$.prototype,"_selectedWindowSensors",2),k([m()],$.prototype,"_windowOpenDelay",2),k([m()],$.prototype,"_windowCloseDelay",2),k([m()],$.prototype,"_climateMode",2),k([m()],$.prototype,"_schedules",2),k([m()],$.prototype,"_scheduleSelectorEntity",2),k([m()],$.prototype,"_comfortHeat",2),k([m()],$.prototype,"_comfortCool",2),k([m()],$.prototype,"_ecoHeat",2),k([m()],$.prototype,"_ecoCool",2),k([m()],$.prototype,"_error",2),k([m()],$.prototype,"_dirty",2),k([m()],$.prototype,"_editingSchedule",2),k([m()],$.prototype,"_editingDevices",2),k([m()],$.prototype,"_editingPresence",2),k([m()],$.prototype,"_selectedPresencePersons",2),k([m()],$.prototype,"_displayName",2),k([m()],$.prototype,"_heatingSystemType",2),$=k([R("rs-room-detail")],$);const Hi=async()=>{var e;if(!customElements.get("ha-entity-picker")){if(!customElements.get("ha-selector")){await customElements.whenDefined("partial-panel-resolver");const t=document.createElement("partial-panel-resolver");t.hass={panels:[{url_path:"tmp",component_name:"config"}]},t._updateRoutes(),await t.routerOptions.routes.tmp.load(),await customElements.whenDefined("ha-panel-config"),await document.createElement("ha-panel-config").routerOptions.routes.automation.load()}if(!customElements.get("ha-entity-picker"))try{await(await(await window.loadCardHelpers()).createCardElement({type:"entities",entities:[]})).constructor.getConfigElement()}catch{}if(!customElements.get("ha-entity-picker"))try{await Promise.race([customElements.whenDefined("ha-selector"),new Promise((s,o)=>setTimeout(()=>o(new Error("timeout")),1e4))]);const t=(e=document.querySelector("home-assistant"))==null?void 0:e.hass,i=document.createElement("div");i.style.cssText="position:fixed;left:-9999px;opacity:0;pointer-events:none",document.body.appendChild(i);try{const s=document.createElement("ha-selector");s.hass=t,s.selector={entity:{}},i.appendChild(s),await Promise.race([customElements.whenDefined("ha-entity-picker"),new Promise(o=>setTimeout(o,5e3))])}finally{i.remove()}}catch{}if(await customElements.whenDefined("ha-card"),!customElements.get("ha-date-range-picker"))try{await(await window.loadCardHelpers()).createCardElement({type:"energy-date-selection",entities:[]}),await Promise.race([customElements.whenDefined("ha-date-range-picker"),new Promise((i,s)=>setTimeout(s,5e3))])}catch{}if(!customElements.get("ha-chart-base"))try{await(await window.loadCardHelpers()).createCardElement({type:"statistics-graph",entities:[]}),await Promise.race([customElements.whenDefined("ha-chart-base"),new Promise((i,s)=>setTimeout(s,5e3))])}catch{}}};var Oi=Object.defineProperty,Li=Object.getOwnPropertyDescriptor,W=(e,t,i,s)=>{for(var o=s>1?void 0:s?Li(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Oi(t,i,o),o};let L=class extends z{constructor(){super(...arguments),this.rooms={},this.groupByFloor=!1,this.climateControlActive=!0,this.learningDisabledRooms=[],this.scheduleOffAction="eco",this.vacationActive=!1,this.vacationTemp=15,this.vacationUntil="",this.presenceEnabled=!1,this.presencePersons=[],this.presenceAwayAction="eco",this.valveProtectionEnabled=!1,this.valveProtectionInterval=7,this._showLearningExceptions=!1}_fire(e,t){this.dispatchEvent(new CustomEvent("setting-changed",{detail:{key:e,value:t},bubbles:!0,composed:!0}))}render(){const e=this.hass.language,t=Object.entries(this.rooms).map(([n])=>{var a,d;return{areaId:n,name:((d=(a=this.hass.areas)==null?void 0:a[n])==null?void 0:d.name)??n}}).sort((n,a)=>n.name.localeCompare(a.name)),i=Object.keys(this.rooms),s=i.length===0||this.learningDisabledRooms.length<i.length,o=this.learningDisabledRooms.filter(n=>i.includes(n)).length;return l`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:power"></ha-icon>
            <span>${r("settings.general_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          ${this.hass.floors&&Object.keys(this.hass.floors).length>0?l`<div class="settings-section first">
                <div class="toggle-row">
                  <div class="toggle-text">
                    <span class="toggle-label">${r("settings.group_by_floor",e)}</span>
                  </div>
                  <ha-switch
                    .checked=${this.groupByFloor}
                    @change=${n=>this._fire("groupByFloor",n.target.checked)}
                  ></ha-switch>
                </div>
              </div>`:p}
          <div class="settings-section ${this.hass.floors&&Object.keys(this.hass.floors).length>0?"":"first"}">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${r("settings.climate_control_active",e)}</span>
                <span class="toggle-hint">${r("settings.climate_control_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this.climateControlActive}
                @change=${n=>this._fire("climateControlActive",n.target.checked)}
              ></ha-switch>
            </div>
            <ha-select
              .label=${r("schedule.off_action_label",e)}
              .value=${this.scheduleOffAction}
              fixedMenuPosition
              @selected=${n=>{const a=pe(n);a&&a!==this.scheduleOffAction&&this._fire("scheduleOffAction",a)}}
              @closed=${n=>n.stopPropagation()}
              style="margin-top: 8px"
            >
              <ha-list-item value="eco">${r("schedule.off_action_eco",e)}</ha-list-item>
              <ha-list-item value="off">${r("schedule.off_action_off",e)}</ha-list-item>
            </ha-select>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${r("settings.learning_title",e)}</span>
                <span class="toggle-hint">${r("settings.learning_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${s}
                @change=${n=>{const a=n.target.checked;this._fire("learningDisabledRooms",a?[]:Object.keys(this.rooms)),a||(this._showLearningExceptions=!1)}}
              ></ha-switch>
            </div>
            ${s&&t.length>0?l`
                  <button class="exceptions-link" @click=${()=>{this._showLearningExceptions=!this._showLearningExceptions}}>
                    <span>${o>0?`${o} ${r(o===1?"settings.learning_room_paused":"settings.learning_rooms_paused",e)}`:r("settings.learning_exceptions",e)}</span>
                    <ha-icon
                      icon=${this._showLearningExceptions?"mdi:chevron-up":"mdi:chevron-down"}
                      style="--mdc-icon-size: 16px"
                    ></ha-icon>
                  </button>
                  ${this._showLearningExceptions?l`
                        <div class="room-toggles">
                          ${t.map(n=>l`
                              <div class="room-toggle-row">
                                <span class="room-toggle-name">${n.name}</span>
                                <ha-switch
                                  .checked=${!this.learningDisabledRooms.includes(n.areaId)}
                                  @change=${a=>{const d=!a.target.checked,c=new Set(this.learningDisabledRooms);d?c.add(n.areaId):c.delete(n.areaId),this._fire("learningDisabledRooms",[...c])}}
                                ></ha-switch>
                              </div>
                            `)}
                        </div>
                      `:p}
              `:p}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:airplane" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${r("vacation.title",e)}
                </span>
                <span class="toggle-hint">${r("vacation.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this.vacationActive}
                @change=${n=>{const a=n.target.checked;this._fire("vacationActive",a),a||this._fire("vacationUntil","")}}
              ></ha-switch>
            </div>
            ${this.vacationActive?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${this.vacationUntil}
                        .label=${r("vacation.end_date",e)}
                        type="datetime-local"
                        @change=${n=>this._fire("vacationUntil",n.target.value)}
                      ></ha-textfield>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(O(this.vacationTemp,this.hass))}
                        .label=${r("vacation.setback_temp",e)}
                        .suffix=${f(this.hass)}
                        type="number"
                        step=${re(this.hass)}
                        min=${H(5,25,this.hass).min}
                        max=${H(5,25,this.hass).max}
                        @change=${n=>{const a=parseFloat(n.target.value);isNaN(a)||this._fire("vacationTemp",ye(a,this.hass))}}
                      ></ha-textfield>
                    </div>
                  </div>
                `:p}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:home-account" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${r("presence.title",e)}
                </span>
                <span class="toggle-hint">${r("presence.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this.presenceEnabled}
                @change=${n=>this._fire("presenceEnabled",n.target.checked)}
              ></ha-switch>
            </div>
            ${this.presenceEnabled?l`
                  <div class="room-toggles" style="gap: 8px">
                    <span class="field-hint" style="margin-bottom: 4px">${r("presence.hint_detail",e)}</span>
                    ${this.presencePersons.length>0?l`
                      <div class="presence-person-list">
                        ${this.presencePersons.map(n=>{var d,c;const a=((c=(d=this.hass.states[n])==null?void 0:d.attributes)==null?void 0:c.friendly_name)??n.split(".").slice(1).join(".");return l`
                            <div class="presence-person-row">
                              <ha-icon icon="mdi:account" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                              <span class="presence-person-name">${a}</span>
                              <ha-icon-button
                                .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                                @click=${()=>this._fire("presencePersons",this.presencePersons.filter(u=>u!==n))}
                              ></ha-icon-button>
                            </div>
                          `})}
                      </div>
                    `:p}
                    <ha-entity-picker
                      .hass=${this.hass}
                      .includeDomains=${["person","device_tracker","binary_sensor","input_boolean"]}
                      .entityFilter=${n=>!this.presencePersons.includes(n.entity_id)}
                      .label=${r("presence.add_entity",e)}
                      @value-changed=${n=>{var c;const a=(c=n.detail)==null?void 0:c.value;a&&!this.presencePersons.includes(a)&&this._fire("presencePersons",[...this.presencePersons,a]);const d=n.target;d.value=""}}
                    ></ha-entity-picker>
                    <ha-select
                      .label=${r("presence.away_action_label",e)}
                      .value=${this.presenceAwayAction}
                      fixedMenuPosition
                      @selected=${n=>{const a=pe(n);a&&a!==this.presenceAwayAction&&this._fire("presenceAwayAction",a)}}
                      @closed=${n=>n.stopPropagation()}
                      style="margin-top: 8px"
                    >
                      <ha-list-item value="eco">${r("presence.away_action_eco",e)}</ha-list-item>
                      <ha-list-item value="off">${r("presence.away_action_off",e)}</ha-list-item>
                    </ha-select>
                  </div>
                `:p}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-refresh" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${r("valve_protection.title",e)}
                </span>
                <span class="toggle-hint">${r("valve_protection.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this.valveProtectionEnabled}
                @change=${n=>this._fire("valveProtectionEnabled",n.target.checked)}
              ></ha-switch>
            </div>
            ${this.valveProtectionEnabled?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.valveProtectionInterval)}
                        .label=${r("valve_protection.interval_label",e)}
                        .suffix=${r("valve_protection.interval_suffix",e)}
                        type="number"
                        step="1"
                        min="1"
                        max="90"
                        @change=${n=>{const a=parseInt(n.target.value,10);!isNaN(a)&&a>=1&&a<=90&&this._fire("valveProtectionInterval",a)}}
                      ></ha-textfield>
                      <span class="field-hint">${r("valve_protection.interval_hint",e)}</span>
                    </div>
                  </div>
                `:p}
          </div>
        </div>
      </ha-card>
    `}};L.styles=D`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .exceptions-link {
      display: inline-flex; align-items: center; gap: 4px;
      background: none; border: none; padding: 8px 0 0; margin: 0;
      cursor: pointer; font-size: 13px; color: var(--primary-color); font-family: inherit;
    }
    .exceptions-link:hover { text-decoration: underline; }

    .room-toggles { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; }
    .room-toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; }
    .room-toggle-name { font-size: 14px; color: var(--primary-text-color); }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    .presence-person-list { display: flex; flex-direction: column; gap: 2px; }
    .presence-person-row {
      display: flex; align-items: center; gap: 10px;
      padding: 4px 8px 4px 12px; border-radius: 8px; background: rgba(0, 0, 0, 0.04);
    }
    .presence-person-name { flex: 1; font-size: 14px; font-weight: 500; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `,W([h({attribute:!1})],L.prototype,"hass",2),W([h({attribute:!1})],L.prototype,"rooms",2),W([h({type:Boolean})],L.prototype,"groupByFloor",2),W([h({type:Boolean})],L.prototype,"climateControlActive",2),W([h({type:Array})],L.prototype,"learningDisabledRooms",2),W([h({type:String})],L.prototype,"scheduleOffAction",2),W([h({type:Boolean})],L.prototype,"vacationActive",2),W([h({type:Number})],L.prototype,"vacationTemp",2),W([h({type:String})],L.prototype,"vacationUntil",2),W([h({type:Boolean})],L.prototype,"presenceEnabled",2),W([h({type:Array})],L.prototype,"presencePersons",2),W([h({type:String})],L.prototype,"presenceAwayAction",2),W([h({type:Boolean})],L.prototype,"valveProtectionEnabled",2),W([h({type:Number})],L.prototype,"valveProtectionInterval",2),W([m()],L.prototype,"_showLearningExceptions",2),L=W([R("rs-settings-general")],L);var Ni=Object.defineProperty,Ii=Object.getOwnPropertyDescriptor,Ee=(e,t,i,s)=>{for(var o=s>1?void 0:s?Ii(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Ni(t,i,o),o};let me=class extends z{constructor(){super(...arguments),this.controlMode="mpc",this.comfortWeight=70,this.outdoorCoolingMin=16,this.outdoorHeatingMax=22,this.predictionEnabled=!0}_fire(e,t){this.dispatchEvent(new CustomEvent("setting-changed",{detail:{key:e,value:t},bubbles:!0,composed:!0}))}render(){const e=this.hass.language;return l`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:tune-variant"></ha-icon>
            <span>${r("settings.control_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <p class="hint">${r("settings.control_mode_hint",e)}</p>
            <div class="radio-group">
              <label class="radio-option" @click=${()=>this._setControlMode("mpc")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this.controlMode==="mpc"}
                ></ha-radio>
                <span>${r("settings.control_mode_mpc",e)}</span>
              </label>
              <label class="radio-option" @click=${()=>this._setControlMode("bangbang")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this.controlMode==="bangbang"}
                ></ha-radio>
                <span>${r("settings.control_mode_simple",e)}</span>
              </label>
            </div>
          </div>

          <div class="settings-section">
            <label class="section-label">${r("settings.comfort_weight",e)}</label>
            <div class="slider-row">
              <span class="slider-label">${r("settings.comfort_weight_efficiency",e)}</span>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                .value=${String(this.comfortWeight)}
                @change=${t=>{const i=parseInt(t.target.value,10);!isNaN(i)&&i!==this.comfortWeight&&this._fire("comfortWeight",i)}}
              />
              <span class="slider-label">${r("settings.comfort_weight_comfort",e)}</span>
            </div>
          </div>

          <div class="settings-section">
            <p class="hint">${r("settings.smart_control_hint",e)}</p>
            <div class="threshold-grid">
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(O(this.outdoorCoolingMin,this.hass))}
                  .label=${r("settings.outdoor_cooling_min",e)}
                  .suffix=${f(this.hass)}
                  type="number"
                  step=${re(this.hass)}
                  min=${H(-10,40,this.hass).min}
                  max=${H(-10,40,this.hass).max}
                  @change=${t=>{const i=parseFloat(t.target.value);isNaN(i)||this._fire("outdoorCoolingMin",ye(i,this.hass))}}
                ></ha-textfield>
                <span class="field-hint">${r("settings.outdoor_cooling_min_hint",e)}</span>
              </div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(O(this.outdoorHeatingMax,this.hass))}
                  .label=${r("settings.outdoor_heating_max",e)}
                  .suffix=${f(this.hass)}
                  type="number"
                  step=${re(this.hass)}
                  min=${H(0,40,this.hass).min}
                  max=${H(0,40,this.hass).max}
                  @change=${t=>{const i=parseFloat(t.target.value);isNaN(i)||this._fire("outdoorHeatingMax",ye(i,this.hass))}}
                ></ha-textfield>
                <span class="field-hint">${r("settings.outdoor_heating_max_hint",e)}</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${r("settings.prediction_enabled",e)}</span>
                <span class="toggle-hint">${r("settings.prediction_enabled_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this.predictionEnabled}
                @change=${t=>this._fire("predictionEnabled",t.target.checked)}
              ></ha-switch>
            </div>
          </div>
        </div>
      </ha-card>
    `}_setControlMode(e){this.controlMode!==e&&this._fire("controlMode",e)}};me.styles=D`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child { border-top: none; }

    .hint { color: var(--secondary-text-color); font-size: 13px; margin: 0 0 12px; }
    .section-label { display: block; margin-bottom: 8px; font-size: 14px; color: var(--primary-text-color); }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .radio-group { display: flex; flex-direction: column; gap: 8px; }
    .radio-option { display: flex; align-items: center; gap: 8px; cursor: pointer; }

    .slider-row { display: flex; align-items: center; gap: 8px; }
    .slider-row input[type="range"] { flex: 1; accent-color: var(--primary-color); }
    .slider-label { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
    }
  `,Ee([h({attribute:!1})],me.prototype,"hass",2),Ee([h({type:String})],me.prototype,"controlMode",2),Ee([h({type:Number})],me.prototype,"comfortWeight",2),Ee([h({type:Number})],me.prototype,"outdoorCoolingMin",2),Ee([h({type:Number})],me.prototype,"outdoorHeatingMax",2),Ee([h({type:Boolean})],me.prototype,"predictionEnabled",2),me=Ee([R("rs-settings-control")],me);var Wi=Object.defineProperty,ji=Object.getOwnPropertyDescriptor,Ue=(e,t,i,s)=>{for(var o=s>1?void 0:s?ji(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Wi(t,i,o),o};let Ae=class extends z{constructor(){super(...arguments),this.outdoorTempSensor="",this.outdoorHumiditySensor="",this.weatherEntity="",this._filterTemperature=e=>{var t;return((t=e.attributes)==null?void 0:t.device_class)==="temperature"},this._filterHumidity=e=>{var t;return((t=e.attributes)==null?void 0:t.device_class)==="humidity"}}_fire(e,t){this.dispatchEvent(new CustomEvent("setting-changed",{detail:{key:e,value:t},bubbles:!0,composed:!0}))}_getSensorValue(e){const t=this.hass.states[e];if(!t||t.state==="unavailable"||t.state==="unknown")return null;const i=parseFloat(t.state);return isNaN(i)?null:Math.round(i*10)/10}render(){const e=this.hass.language,t=this.outdoorTempSensor?this._getSensorValue(this.outdoorTempSensor):null,i=this.outdoorHumiditySensor?this._getSensorValue(this.outdoorHumiditySensor):null;return l`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:thermometer"></ha-icon>
            <span>${r("settings.sensors_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <div class="sensor-grid">
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this.outdoorTempSensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterTemperature}
                  .label=${r("settings.outdoor_sensor_label",e)}
                  allow-custom-entity
                  @value-changed=${s=>{var n;const o=((n=s.detail)==null?void 0:n.value)??"";o!==this.outdoorTempSensor&&this._fire("outdoorTempSensor",o)}}
                ></ha-entity-picker>
                ${t!==null?l`<div class="current-value">
                      ${r("settings.outdoor_current",e,{temp:t.toFixed(1),unit:f(this.hass)})}
                    </div>`:this.outdoorTempSensor?l`<div class="current-value muted">${r("settings.outdoor_waiting",e)}</div>`:p}
              </div>
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this.outdoorHumiditySensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterHumidity}
                  .label=${r("settings.outdoor_humidity_label",e)}
                  allow-custom-entity
                  @value-changed=${s=>{var n;const o=((n=s.detail)==null?void 0:n.value)??"";o!==this.outdoorHumiditySensor&&this._fire("outdoorHumiditySensor",o)}}
                ></ha-entity-picker>
                ${i!==null?l`<div class="current-value">
                      ${r("settings.outdoor_humidity_current",e,{value:String(i)})}
                    </div>`:this.outdoorHumiditySensor?l`<div class="current-value muted">${r("settings.outdoor_waiting",e)}</div>`:p}
              </div>
            </div>
          </div>

          <div class="settings-section">
            <ha-entity-picker
              .hass=${this.hass}
              .value=${this.weatherEntity}
              .includeDomains=${["weather"]}
              .label=${r("settings.weather_entity",e)}
              allow-custom-entity
              @value-changed=${s=>{var n;const o=((n=s.detail)==null?void 0:n.value)??"";o!==this.weatherEntity&&this._fire("weatherEntity",o)}}
            ></ha-entity-picker>
            <span class="field-hint">${r("settings.weather_entity_hint",e)}</span>
          </div>
        </div>
      </ha-card>
    `}};Ae.styles=D`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child { border-top: none; }

    .sensor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .current-value { margin-top: 8px; font-size: 14px; color: var(--primary-text-color); }
    .current-value.muted { color: var(--secondary-text-color); }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    @media (max-width: 600px) {
      .sensor-grid { grid-template-columns: 1fr; }
    }
  `,Ue([h({attribute:!1})],Ae.prototype,"hass",2),Ue([h({type:String})],Ae.prototype,"outdoorTempSensor",2),Ue([h({type:String})],Ae.prototype,"outdoorHumiditySensor",2),Ue([h({type:String})],Ae.prototype,"weatherEntity",2),Ae=Ue([R("rs-settings-sensors")],Ae);var Ui=Object.defineProperty,Fi=Object.getOwnPropertyDescriptor,se=(e,t,i,s)=>{for(var o=s>1?void 0:s?Fi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Ui(t,i,o),o};let q=class extends z{constructor(){super(...arguments),this.moldDetectionEnabled=!1,this.moldHumidityThreshold=70,this.moldSustainedMinutes=30,this.moldNotificationCooldown=60,this.moldNotificationsEnabled=!0,this.moldNotificationTargets=[],this.moldPreventionEnabled=!1,this.moldPreventionIntensity="medium",this.moldPreventionNotify=!1}_fire(e,t){this.dispatchEvent(new CustomEvent("setting-changed",{detail:{key:e,value:t},bubbles:!0,composed:!0}))}render(){const e=this.hass.language;return l`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:water-alert"></ha-icon>
            <span>${r("mold.title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <!-- Detection section -->
          <div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:bell-alert" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${r("mold.detection",e)}
                </span>
                <span class="toggle-hint">${r("mold.detection_desc",e)}</span>
              </div>
              <ha-switch
                .checked=${this.moldDetectionEnabled}
                @change=${t=>this._fire("moldDetectionEnabled",t.target.checked)}
              ></ha-switch>
            </div>
            ${this.moldDetectionEnabled?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldHumidityThreshold)}
                        .label=${r("mold.threshold",e)}
                        .suffix=${"%"}
                        type="number" step="1" min="50" max="90"
                        @change=${t=>{const i=parseFloat(t.target.value);!isNaN(i)&&i>=50&&i<=90&&this._fire("moldHumidityThreshold",i)}}
                      ></ha-textfield>
                      <span class="field-hint">${r("mold.threshold_hint",e)}</span>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldSustainedMinutes)}
                        .label=${r("mold.sustained",e)}
                        .suffix=${"min"}
                        type="number" step="5" min="5" max="120"
                        @change=${t=>{const i=parseInt(t.target.value,10);!isNaN(i)&&i>=5&&i<=120&&this._fire("moldSustainedMinutes",i)}}
                      ></ha-textfield>
                      <span class="field-hint">${r("mold.sustained_hint",e)}</span>
                    </div>
                  </div>
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this.moldNotificationCooldown)}
                        .label=${r("mold.cooldown",e)}
                        .suffix=${"min"}
                        type="number" step="5" min="10" max="1440"
                        @change=${t=>{const i=parseInt(t.target.value,10);!isNaN(i)&&i>=10&&i<=1440&&this._fire("moldNotificationCooldown",i)}}
                      ></ha-textfield>
                      <span class="field-hint">${r("mold.cooldown_hint",e)}</span>
                    </div>
                  </div>
                `:p}
          </div>

          <!-- Prevention section -->
          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-check" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${r("mold.prevention",e)}
                </span>
                <span class="toggle-hint">${r("mold.prevention_desc",e)}</span>
              </div>
              <ha-switch
                .checked=${this.moldPreventionEnabled}
                @change=${t=>this._fire("moldPreventionEnabled",t.target.checked)}
              ></ha-switch>
            </div>
            ${this.moldPreventionEnabled?l`
                  <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 4px;">
                    <ha-select
                      style="width: 100%;"
                      .value=${this.moldPreventionIntensity}
                      .label=${r("mold.intensity",e)}
                      @selected=${t=>{const i=pe(t);i&&i!==this.moldPreventionIntensity&&this._fire("moldPreventionIntensity",i)}}
                      @closed=${t=>t.stopPropagation()}
                    >
                      <ha-list-item value="light">${r("mold.intensity_light",e,{delta:String(ae(1,this.hass)),unit:f(this.hass)})}</ha-list-item>
                      <ha-list-item value="medium">${r("mold.intensity_medium",e,{delta:String(ae(2,this.hass)),unit:f(this.hass)})}</ha-list-item>
                      <ha-list-item value="strong">${r("mold.intensity_strong",e,{delta:String(ae(3,this.hass)),unit:f(this.hass)})}</ha-list-item>
                    </ha-select>
                    <span class="field-hint">${r("mold.intensity_hint",e)}</span>
                  </div>
                `:p}
          </div>

          <!-- Notifications section -->
          ${this.moldDetectionEnabled||this.moldPreventionEnabled?l`
                <div class="settings-section">
                  <div class="toggle-row">
                    <div class="toggle-text">
                      <span class="toggle-label">
                        <ha-icon icon="mdi:bell-outline" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                        ${r("mold.notifications_enabled",e)}
                        <ha-icon
                          icon="mdi:alert-circle-outline"
                          style="--mdc-icon-size: 14px; vertical-align: middle; margin-left: 4px; color: var(--warning-color, #ffa600)"
                          title="${r("mold.notifications_beta_hint",e)}"
                        ></ha-icon>
                      </span>
                      <span class="toggle-hint">${r("mold.notifications_enabled_hint",e)}</span>
                    </div>
                    <ha-switch
                      .checked=${this.moldNotificationsEnabled}
                      @change=${t=>this._fire("moldNotificationsEnabled",t.target.checked)}
                    ></ha-switch>
                  </div>
                  ${this.moldNotificationsEnabled?l`
                  <p class="hint" style="margin-top: 12px">${r("mold.notifications_desc",e)}</p>

                  <div class="presence-person-list">
                    ${this.moldNotificationTargets.map((t,i)=>{var o,n;const s=t.entity_id?((n=(o=this.hass.states[t.entity_id])==null?void 0:o.attributes)==null?void 0:n.friendly_name)??t.entity_id.replace("notify.",""):r("mold.target_unnamed",e);return l`
                        <div class="mold-target-card">
                          <div class="mold-target-header">
                            <ha-icon icon="mdi:bell" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                            <span>${s}</span>
                            <ha-icon-button
                              .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                              @click=${()=>{this._fire("moldNotificationTargets",this.moldNotificationTargets.filter((a,d)=>d!==i))}}
                            ></ha-icon-button>
                          </div>
                          <div class="mold-target-detail">
                            <ha-entity-picker
                              .hass=${this.hass}
                              .value=${t.person_entity}
                              .includeDomains=${["person"]}
                              .label=${r("mold.target_person",e)}
                              allow-custom-entity
                              @value-changed=${a=>{var c;const d=[...this.moldNotificationTargets];d[i]={...d[i],person_entity:((c=a.detail)==null?void 0:c.value)??""},this._fire("moldNotificationTargets",d)}}
                            ></ha-entity-picker>
                            <ha-select
                              .value=${t.notify_when}
                              @selected=${a=>{const d=pe(a);if(!d)return;const c=[...this.moldNotificationTargets];c[i]={...c[i],notify_when:d},this._fire("moldNotificationTargets",c)}}
                              @closed=${a=>a.stopPropagation()}
                            >
                              <ha-list-item value="always">${r("mold.target_when_always",e)}</ha-list-item>
                              <ha-list-item value="home_only">${r("mold.target_when_home",e)}</ha-list-item>
                            </ha-select>
                          </div>
                        </div>
                      `})}
                  </div>

                  <div style="margin-top: 8px">
                    <ha-entity-picker
                      .hass=${this.hass}
                      .value=${""}
                      .includeDomains=${["notify"]}
                      .label=${r("mold.add_target_label",e)}
                      allow-custom-entity
                      @value-changed=${t=>{var o;const i=((o=t.detail)==null?void 0:o.value)??"";if(!i)return;this._fire("moldNotificationTargets",[...this.moldNotificationTargets,{entity_id:i,person_entity:"",notify_when:"always"}]);const s=t.target;s&&(s.value="")}}
                    ></ha-entity-picker>
                    <span class="field-hint">${r("mold.add_target_hint",e)}</span>
                  </div>

                  ${this.moldPreventionEnabled?l`
                        <div class="toggle-row" style="margin-top: 12px">
                          <div class="toggle-text">
                            <span class="toggle-label">${r("mold.prevention_notify",e)}</span>
                            <span class="toggle-hint">${r("mold.prevention_notify_hint",e)}</span>
                          </div>
                          <ha-switch
                            .checked=${this.moldPreventionNotify}
                            @change=${t=>this._fire("moldPreventionNotify",t.target.checked)}
                          ></ha-switch>
                        </div>
                      `:p}
                    `:p}
                </div>
              `:p}
        </div>
      </ha-card>
    `}};q.styles=D`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; }

    .hint { color: var(--secondary-text-color); font-size: 13px; margin: 0 0 12px; }

    .toggle-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .toggle-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }
    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .threshold-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .threshold-field { display: flex; flex-direction: column; gap: 4px; }
    .threshold-field ha-textfield { width: 100%; }
    .field-hint { color: var(--secondary-text-color); font-size: 12px; }

    .presence-person-list { display: flex; flex-direction: column; gap: 2px; }

    .mold-target-card {
      display: flex; flex-direction: column; gap: 4px;
      padding: 8px 8px 8px 12px; border-radius: 8px; background: rgba(0, 0, 0, 0.04);
    }
    .mold-target-header { display: flex; align-items: center; gap: 8px; }
    .mold-target-header span { flex: 1; font-size: 14px; font-weight: 500; }
    .mold-target-detail { display: flex; gap: 8px; align-items: center; padding-left: 26px; }
    .mold-target-detail ha-entity-picker { flex: 1; }
    .mold-target-detail ha-select { min-width: 120px; }

    @media (max-width: 600px) {
      .threshold-grid { grid-template-columns: 1fr; }
      .mold-target-detail { flex-direction: column; padding-left: 0; }
    }
  `,se([h({attribute:!1})],q.prototype,"hass",2),se([h({type:Boolean})],q.prototype,"moldDetectionEnabled",2),se([h({type:Number})],q.prototype,"moldHumidityThreshold",2),se([h({type:Number})],q.prototype,"moldSustainedMinutes",2),se([h({type:Number})],q.prototype,"moldNotificationCooldown",2),se([h({type:Boolean})],q.prototype,"moldNotificationsEnabled",2),se([h({type:Array})],q.prototype,"moldNotificationTargets",2),se([h({type:Boolean})],q.prototype,"moldPreventionEnabled",2),se([h({type:String})],q.prototype,"moldPreventionIntensity",2),se([h({type:Boolean})],q.prototype,"moldPreventionNotify",2),q=se([R("rs-settings-mold")],q);var Bi=Object.defineProperty,Vi=Object.getOwnPropertyDescriptor,Qe=(e,t,i,s)=>{for(var o=s>1?void 0:s?Vi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Bi(t,i,o),o};let Pe=class extends z{constructor(){super(...arguments),this.rooms={},this._resetSelectedRoom=""}render(){const e=this.hass.language,t=Object.entries(this.rooms).map(([i])=>{var s,o;return{areaId:i,name:((o=(s=this.hass.areas)==null?void 0:s[i])==null?void 0:o.name)??i}}).sort((i,s)=>i.name.localeCompare(s.name));return l`
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:restart"></ha-icon>
            <span>${r("settings.reset_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <p class="hint">${r("settings.reset_hint",e)}</p>

          <div class="settings-section first">
            <div class="reset-row">
              <div class="reset-text">
                <span class="toggle-label">${r("settings.reset_all_label",e)}</span>
                <span class="toggle-hint">${r("settings.reset_all_hint",e)}</span>
              </div>
              <button class="reset-btn" @click=${this._resetAllModels}>
                <ha-icon icon="mdi:restart-alert"></ha-icon>
                ${r("settings.reset_all_btn",e)}
              </button>
            </div>
          </div>

          <div class="settings-section">
            <div class="reset-text" style="margin-bottom: 12px">
              <span class="toggle-label">${r("settings.reset_room_label",e)}</span>
              <span class="toggle-hint">${r("settings.reset_room_hint",e)}</span>
            </div>
            ${t.length>0?l`
                  <div class="reset-room-row">
                    <ha-select
                      .value=${this._resetSelectedRoom}
                      .label=${r("settings.reset_room_select",e)}
                      @selected=${i=>{this._resetSelectedRoom=pe(i)}}
                      @closed=${i=>i.stopPropagation()}
                    >
                      ${t.map(i=>l`<ha-list-item .value=${i.areaId}>${i.name}</ha-list-item>`)}
                    </ha-select>
                    ${this._resetSelectedRoom?l`<ha-icon-button
                          .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                          @click=${()=>{this._resetSelectedRoom=""}}
                        ></ha-icon-button>`:p}
                    <button
                      class="reset-btn"
                      ?disabled=${!this._resetSelectedRoom}
                      @click=${()=>this._resetSelectedRoom&&this._resetRoomModel(this._resetSelectedRoom)}
                    >
                      <ha-icon icon="mdi:restart"></ha-icon>
                      ${r("settings.reset_btn",e)}
                    </button>
                  </div>
                `:l`<p class="hint">${r("settings.reset_no_rooms",e)}</p>`}
          </div>
        </div>
      </ha-card>
    `}async _resetRoomModel(e){const t=this.hass.language;if(confirm(r("settings.reset_room_confirm",t)))try{J(this,"saving"),await this.hass.callWS({type:"roommind/thermal/reset",area_id:e}),J(this,"saved")}catch{J(this,"error")}}async _resetAllModels(){const e=this.hass.language;if(confirm(r("settings.reset_all_confirm",e)))try{J(this,"saving"),await this.hass.callWS({type:"roommind/thermal/reset_all"}),J(this,"saved")}catch{J(this,"error")}}};Pe.styles=D`
    :host { display: block; }

    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 16px 0; font-size: 16px; font-weight: 500;
    }
    .header-title { display: flex; align-items: center; gap: 8px; --mdc-icon-size: 20px; }
    .card-content { padding: 8px 16px 16px; }

    .hint { color: var(--secondary-text-color); font-size: 13px; margin: 0 0 12px; }

    .settings-section { padding: 16px 0; border-top: 1px solid var(--divider-color); }
    .settings-section:first-child, .settings-section.first { border-top: none; }

    .toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
    .toggle-hint { font-size: 13px; color: var(--secondary-text-color); line-height: 1.4; }

    .reset-row {
      display: flex; justify-content: space-between; align-items: center; gap: 16px;
    }
    .reset-text { display: flex; flex-direction: column; gap: 4px; flex: 1; }

    .reset-btn {
      display: flex; align-items: center; gap: 6px;
      padding: 8px 14px; border: 1px solid var(--error-color, #d32f2f); border-radius: 8px;
      background: transparent; color: var(--error-color, #d32f2f);
      font-size: 13px; font-family: inherit; cursor: pointer;
      transition: background 0.15s; --mdc-icon-size: 16px; white-space: nowrap;
    }
    .reset-btn:hover { background: rgba(211, 47, 47, 0.08); }
    .reset-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .reset-btn:disabled:hover { background: transparent; }

    .reset-room-row { display: flex; align-items: center; gap: 12px; }
    .reset-room-row ha-select { flex: 1; }

    @media (max-width: 600px) {
      .reset-row { flex-direction: column; align-items: flex-start; gap: 12px; }
    }
  `,Qe([h({attribute:!1})],Pe.prototype,"hass",2),Qe([h({attribute:!1})],Pe.prototype,"rooms",2),Qe([m()],Pe.prototype,"_resetSelectedRoom",2),Pe=Qe([R("rs-settings-reset")],Pe);var Ki=Object.defineProperty,Zi=Object.getOwnPropertyDescriptor,x=(e,t,i,s)=>{for(var o=s>1?void 0:s?Zi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Ki(t,i,o),o};let b=class extends z{constructor(){super(...arguments),this.rooms={},this._groupByFloor=!1,this._climateControlActive=!0,this._learningDisabledRooms=[],this._outdoorTempSensor="",this._outdoorHumiditySensor="",this._outdoorCoolingMin=16,this._outdoorHeatingMax=22,this._controlMode="mpc",this._comfortWeight=70,this._weatherEntity="",this._predictionEnabled=!0,this._vacationActive=!1,this._vacationTemp=15,this._vacationUntil="",this._presenceEnabled=!1,this._presencePersons=[],this._presenceAwayAction="eco",this._scheduleOffAction="eco",this._valveProtectionEnabled=!1,this._valveProtectionInterval=7,this._moldDetectionEnabled=!1,this._moldHumidityThreshold=70,this._moldSustainedMinutes=30,this._moldNotificationCooldown=60,this._moldNotificationsEnabled=!0,this._moldNotificationTargets=[],this._moldPreventionEnabled=!1,this._moldPreventionIntensity="medium",this._moldPreventionNotify=!1,this._loaded=!1}connectedCallback(){super.connectedCallback(),this._loadSettings()}disconnectedCallback(){super.disconnectedCallback(),this._saveDebounce&&clearTimeout(this._saveDebounce)}async _loadSettings(){try{const t=(await this.hass.callWS({type:"roommind/settings/get"})).settings;this._groupByFloor=t.group_by_floor??!1,this._climateControlActive=t.climate_control_active??!0,this._learningDisabledRooms=t.learning_disabled_rooms??[],this._outdoorTempSensor=t.outdoor_temp_sensor??"",this._outdoorHumiditySensor=t.outdoor_humidity_sensor??"",this._outdoorCoolingMin=t.outdoor_cooling_min??16,this._outdoorHeatingMax=t.outdoor_heating_max??22,this._controlMode=t.control_mode??"mpc",this._comfortWeight=t.comfort_weight??70,this._weatherEntity=t.weather_entity??"",this._predictionEnabled=t.prediction_enabled??!0;const i=t.vacation_until;this._vacationActive=!!(i&&i>Date.now()/1e3),this._vacationTemp=t.vacation_temp??15,i&&i>Date.now()/1e3&&(this._vacationUntil=this._tsToDatetimeLocal(i)),this._presenceEnabled=t.presence_enabled??!1,this._presencePersons=t.presence_persons??[],this._presenceAwayAction=t.presence_away_action??"eco",this._scheduleOffAction=t.schedule_off_action??"eco",this._valveProtectionEnabled=t.valve_protection_enabled??!1,this._valveProtectionInterval=t.valve_protection_interval_days??7,this._moldDetectionEnabled=t.mold_detection_enabled??!1,this._moldHumidityThreshold=t.mold_humidity_threshold??70,this._moldSustainedMinutes=t.mold_sustained_minutes??30,this._moldNotificationCooldown=t.mold_notification_cooldown??60,this._moldNotificationsEnabled=t.mold_notifications_enabled??!0,this._moldNotificationTargets=t.mold_notification_targets??[],this._moldPreventionEnabled=t.mold_prevention_enabled??!1,this._moldPreventionIntensity=t.mold_prevention_intensity??"medium",this._moldPreventionNotify=t.mold_prevention_notify_enabled??!1}catch(e){console.debug("[RoomMind] loadSettings:",e)}finally{this._loaded=!0}}render(){return this._loaded?l`
      <div class="left-column">
        <rs-settings-general
          .hass=${this.hass}
          .rooms=${this.rooms}
          .groupByFloor=${this._groupByFloor}
          .climateControlActive=${this._climateControlActive}
          .learningDisabledRooms=${this._learningDisabledRooms}
          .scheduleOffAction=${this._scheduleOffAction}
          .vacationActive=${this._vacationActive}
          .vacationTemp=${this._vacationTemp}
          .vacationUntil=${this._vacationUntil}
          .presenceEnabled=${this._presenceEnabled}
          .presencePersons=${this._presencePersons}
          .presenceAwayAction=${this._presenceAwayAction}
          .valveProtectionEnabled=${this._valveProtectionEnabled}
          .valveProtectionInterval=${this._valveProtectionInterval}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-general>
        <rs-settings-control
          .hass=${this.hass}
          .controlMode=${this._controlMode}
          .comfortWeight=${this._comfortWeight}
          .outdoorCoolingMin=${this._outdoorCoolingMin}
          .outdoorHeatingMax=${this._outdoorHeatingMax}
          .predictionEnabled=${this._predictionEnabled}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-control>
      </div>
      <div class="right-column">
        <rs-settings-sensors
          .hass=${this.hass}
          .outdoorTempSensor=${this._outdoorTempSensor}
          .outdoorHumiditySensor=${this._outdoorHumiditySensor}
          .weatherEntity=${this._weatherEntity}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-sensors>
        <rs-settings-mold
          .hass=${this.hass}
          .moldDetectionEnabled=${this._moldDetectionEnabled}
          .moldHumidityThreshold=${this._moldHumidityThreshold}
          .moldSustainedMinutes=${this._moldSustainedMinutes}
          .moldNotificationCooldown=${this._moldNotificationCooldown}
          .moldNotificationsEnabled=${this._moldNotificationsEnabled}
          .moldNotificationTargets=${this._moldNotificationTargets}
          .moldPreventionEnabled=${this._moldPreventionEnabled}
          .moldPreventionIntensity=${this._moldPreventionIntensity}
          .moldPreventionNotify=${this._moldPreventionNotify}
          @setting-changed=${this._onSettingChanged}
        ></rs-settings-mold>
        <rs-settings-reset
          .hass=${this.hass}
          .rooms=${this.rooms}
        ></rs-settings-reset>
      </div>
    `:l`<div class="loading">${r("panel.loading",this.hass.language)}</div>`}_onSettingChanged(e){const{key:t,value:i}=e.detail;this[`_${t}`]=i,this._autoSave()}_tsToDatetimeLocal(e){const t=new Date(e*1e3),i=s=>String(s).padStart(2,"0");return`${t.getFullYear()}-${i(t.getMonth()+1)}-${i(t.getDate())}T${i(t.getHours())}:${i(t.getMinutes())}`}_autoSave(){this._saveDebounce&&clearTimeout(this._saveDebounce),this._saveDebounce=setTimeout(()=>this._doSave(),500)}async _doSave(){J(this,"saving");try{await this.hass.callWS({type:"roommind/settings/save",group_by_floor:this._groupByFloor,climate_control_active:this._climateControlActive,learning_disabled_rooms:this._learningDisabledRooms,outdoor_temp_sensor:this._outdoorTempSensor,outdoor_humidity_sensor:this._outdoorHumiditySensor,outdoor_cooling_min:this._outdoorCoolingMin,outdoor_heating_max:this._outdoorHeatingMax,control_mode:this._controlMode,comfort_weight:this._comfortWeight,weather_entity:this._weatherEntity,prediction_enabled:this._predictionEnabled,vacation_temp:this._vacationTemp,vacation_until:this._vacationActive&&this._vacationUntil?new Date(this._vacationUntil).getTime()/1e3:null,presence_enabled:this._presenceEnabled,presence_persons:this._presencePersons.filter(e=>e),presence_away_action:this._presenceAwayAction,schedule_off_action:this._scheduleOffAction,valve_protection_enabled:this._valveProtectionEnabled,valve_protection_interval_days:this._valveProtectionInterval,mold_detection_enabled:this._moldDetectionEnabled,mold_humidity_threshold:this._moldHumidityThreshold,mold_sustained_minutes:this._moldSustainedMinutes,mold_notification_cooldown:this._moldNotificationCooldown,mold_notifications_enabled:this._moldNotificationsEnabled,mold_notification_targets:this._moldNotificationTargets.filter(e=>e.entity_id),mold_prevention_enabled:this._moldPreventionEnabled,mold_prevention_intensity:this._moldPreventionIntensity,mold_prevention_notify_enabled:this._moldPreventionNotify,mold_prevention_notify_targets:this._moldPreventionNotify?this._moldNotificationTargets.filter(e=>e.entity_id):[]}),J(this,"saved")}catch{J(this,"error")}}};b.styles=D`
    :host {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .left-column,
    .right-column {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .loading {
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    @media (max-width: 600px) {
      :host {
        grid-template-columns: 1fr;
      }
    }
  `,x([h({attribute:!1})],b.prototype,"hass",2),x([h({attribute:!1})],b.prototype,"rooms",2),x([m()],b.prototype,"_groupByFloor",2),x([m()],b.prototype,"_climateControlActive",2),x([m()],b.prototype,"_learningDisabledRooms",2),x([m()],b.prototype,"_outdoorTempSensor",2),x([m()],b.prototype,"_outdoorHumiditySensor",2),x([m()],b.prototype,"_outdoorCoolingMin",2),x([m()],b.prototype,"_outdoorHeatingMax",2),x([m()],b.prototype,"_controlMode",2),x([m()],b.prototype,"_comfortWeight",2),x([m()],b.prototype,"_weatherEntity",2),x([m()],b.prototype,"_predictionEnabled",2),x([m()],b.prototype,"_vacationActive",2),x([m()],b.prototype,"_vacationTemp",2),x([m()],b.prototype,"_vacationUntil",2),x([m()],b.prototype,"_presenceEnabled",2),x([m()],b.prototype,"_presencePersons",2),x([m()],b.prototype,"_presenceAwayAction",2),x([m()],b.prototype,"_scheduleOffAction",2),x([m()],b.prototype,"_valveProtectionEnabled",2),x([m()],b.prototype,"_valveProtectionInterval",2),x([m()],b.prototype,"_moldDetectionEnabled",2),x([m()],b.prototype,"_moldHumidityThreshold",2),x([m()],b.prototype,"_moldSustainedMinutes",2),x([m()],b.prototype,"_moldNotificationCooldown",2),x([m()],b.prototype,"_moldNotificationsEnabled",2),x([m()],b.prototype,"_moldNotificationTargets",2),x([m()],b.prototype,"_moldPreventionEnabled",2),x([m()],b.prototype,"_moldPreventionIntensity",2),x([m()],b.prototype,"_moldPreventionNotify",2),x([m()],b.prototype,"_loaded",2),b=x([R("rs-settings")],b);function Mt(e){const t=[...e.history,...e.detail];if(t.length===0)return null;const i="timestamp,datetime,room_temp,outdoor_temp,target_temp,mode,predicted_temp,window_open",s=t.map(o=>{const n=new Date(o.ts*1e3).toISOString(),a=o.room_temp??"",d=o.outdoor_temp??"",c=o.target_temp??"",u=o.predicted_temp??"";return`${o.ts},${n},${a},${d},${c},${o.mode},${u},${o.window_open}`});return[i,...s].join(`
`)}function zt(e,t,i,s){var d,c,u;if(!e||!t)return null;const o=[...t.history??[],...t.detail??[]],n=o.length>0?o[o.length-1]:null,a={version:"0.2.0",area_id:e,room_config:{climate_mode:i==null?void 0:i.climate_mode,has_thermostats:(((d=i==null?void 0:i.thermostats)==null?void 0:d.length)||0)>0,has_acs:(((c=i==null?void 0:i.acs)==null?void 0:c.length)||0)>0,has_temp_sensor:!!(i!=null&&i.temperature_sensor),has_window_sensors:(((u=i==null?void 0:i.window_sensors)==null?void 0:u.length)||0)>0},live:(i==null?void 0:i.live)||{},model:t.model||{},settings:{control_mode:s},outdoor:{temp:(n==null?void 0:n.outdoor_temp)??null}};return JSON.stringify(a,null,2)}function Pt(e,t,i){const s=new Blob([e],{type:`${i};charset=utf-8`}),o=URL.createObjectURL(s),n=document.createElement("a");n.href=o,n.download=t,n.click(),URL.revokeObjectURL(o)}function Dt(e,t,i,s,o,n,a){var y;const d=(y=e==null?void 0:e.areas)==null?void 0:y[i],c=t[i],u=((c==null?void 0:c.display_name)||(d==null?void 0:d.name)||i).replace(/\s+/g,"_").toLowerCase();if(n)return`roommind_${n}_${u}.${a}`;const _=new Date(s).toISOString().slice(0,10),g=new Date(o).toISOString().slice(0,10);return`roommind_${u}_${_}_${g}.${a}`}function Rt(e){var t;return(t=navigator.clipboard)!=null&&t.writeText?(navigator.clipboard.writeText(e).catch(()=>{Ht(e)}),!0):Ht(e)}function Ht(e){const t=document.createElement("textarea");t.value=e,t.style.position="fixed",t.style.opacity="0",document.body.appendChild(t),t.select();let i=!1;try{i=document.execCommand("copy")}catch(s){console.debug("[RoomMind] clipboard fallback:",s)}return document.body.removeChild(t),i}var Gi=Object.defineProperty,qi=Object.getOwnPropertyDescriptor,oe=(e,t,i,s)=>{for(var o=s>1?void 0:s?qi(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Gi(t,i,o),o};let Q=class extends z{constructor(){super(...arguments),this.rooms={},this.selectedRoom="",this.rangeStart=0,this.rangeEnd=0,this.activeQuick="24h",this.data=null,this.controlMode="bangbang",this.language="en",this._openDropdown=null,this._boundCloseDropdowns=this._closeDropdowns.bind(this)}connectedCallback(){super.connectedCallback(),document.addEventListener("click",this._boundCloseDropdowns)}disconnectedCallback(){super.disconnectedCallback(),document.removeEventListener("click",this._boundCloseDropdowns)}updated(e){(e.has("rooms")||e.has("selectedRoom"))&&this.selectedRoom&&this.updateComplete.then(()=>{var i;const t=(i=this.renderRoot)==null?void 0:i.querySelector("ha-select");t&&t.value!==this.selectedRoom&&(t.value=this.selectedRoom)})}render(){const e=this.language,t=this._getConfiguredRooms();return l`
      ${this._renderRoomSelector(t,e)}
      ${this.selectedRoom?this._renderRangeButtons(e):p}
    `}_getConfiguredRooms(){return Object.entries(this.rooms).map(([e,t])=>{var s,o;const i=(o=(s=this.hass)==null?void 0:s.areas)==null?void 0:o[e];return{area_id:e,name:t.display_name||(i==null?void 0:i.name)||e}})}_renderRoomSelector(e,t){return l`
      <div class="selector-row">
        <ha-select
          .value=${this.selectedRoom}
          .label=${r("analytics.select_room",t)}
          .options=${e.map(i=>({value:i.area_id,label:i.name}))}
          naturalMenuWidth
          fixedMenuPosition
          @selected=${this._onRoomSelected}
          @closed=${i=>i.stopPropagation()}
        >
          ${e.map(i=>l`
              <ha-list-item .value=${i.area_id}>${i.name}</ha-list-item>
            `)}
        </ha-select>
      </div>
    `}_renderRangeButtons(e){const t=[{key:"24h",label:r("analytics.range_1d",e),days:1},{key:"2d",label:r("analytics.range_2d",e),days:2},{key:"7d",label:r("analytics.range_7d",e),days:7},{key:"30d",label:r("analytics.range_30d",e),days:30}],i=this.data&&(this.data.history.length>0||this.data.detail.length>0),s=o=>new Date(o).toLocaleString(this.hass.language,{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});return l`
      <div class="range-row">
        <div class="range-controls">
          <div class="range-bar">
            ${t.map(o=>l`
                <button
                  class="range-chip"
                  ?active=${this.activeQuick===o.key}
                  @click=${()=>this._onQuickRange(o.key,o.days)}
                >
                  ${o.label}
                </button>
              `)}
            <div class="range-chip picker-chip ${this.activeQuick===null?"picker-active":""}">
              <ha-date-range-picker
                .hass=${this.hass}
                .startDate=${new Date(this.rangeStart)}
                .endDate=${new Date(this.rangeEnd)}
                .ranges=${!1}
                time-picker
                auto-apply
                minimal
                @value-changed=${this._onDateRangeChanged}
              ></ha-date-range-picker>
            </div>
          </div>
          <span class="date-label ${this.activeQuick===null?"custom-active":""}">${s(this.rangeStart)} – ${s(this.rangeEnd)}</span>
        </div>
        <div class="action-buttons">
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!i}
              @click=${o=>{o.stopPropagation(),this._toggleDropdown("csv")}}
            >
              <ha-icon icon="mdi:download"></ha-icon>
              ${r("analytics.export",e)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown==="csv"?l`<div class="export-dropdown" @click=${o=>o.stopPropagation()}>
                  <button @click=${this._exportCsv}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${r("analytics.export_download",e)}
                  </button>
                  <button @click=${this._copyCsvToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${r("analytics.export_clipboard",e)}
                  </button>
                </div>`:p}
          </div>
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!this.selectedRoom||!this.data}
              @click=${o=>{o.stopPropagation(),this._toggleDropdown("diag")}}
            >
              <ha-icon icon="mdi:bug-outline"></ha-icon>
              ${r("analytics.copy_diagnostics",e)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown==="diag"?l`<div class="export-dropdown" @click=${o=>o.stopPropagation()}>
                  <button @click=${this._exportDiagnostics}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${r("analytics.export_download",e)}
                  </button>
                  <button @click=${this._copyDiagnosticsToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${r("analytics.export_clipboard",e)}
                  </button>
                </div>`:p}
          </div>
        </div>
      </div>
    `}_onRoomSelected(e){const t=pe(e);t&&t!==this.selectedRoom&&this.dispatchEvent(new CustomEvent("room-selected",{detail:{areaId:t},bubbles:!0,composed:!0}))}_onQuickRange(e,t){const i=new Date,s=new Date(i);s.setDate(s.getDate()-(t-1)),s.setHours(0,0,0,0),this.dispatchEvent(new CustomEvent("range-changed",{detail:{activeQuick:e,rangeStart:s.getTime(),rangeEnd:i.getTime(),chartAnchor:i.getTime()},bubbles:!0,composed:!0}))}_onDateRangeChanged(e){const{startDate:t,endDate:i}=e.detail.value;!t||!i||this.dispatchEvent(new CustomEvent("range-changed",{detail:{activeQuick:null,rangeStart:t.getTime(),rangeEnd:i.getTime(),chartAnchor:i.getTime()},bubbles:!0,composed:!0}))}_exportCsv(){if(!this.data)return;const e=Mt(this.data);if(!e)return;const t=Dt(this.hass,this.rooms,this.selectedRoom,this.rangeStart,this.rangeEnd,"","csv");Pt(e,t,"text/csv"),this._openDropdown=null}_exportDiagnostics(){if(!this.data)return;const e=zt(this.selectedRoom,this.data,this.rooms[this.selectedRoom],this.controlMode);if(!e)return;const t=Dt(this.hass,this.rooms,this.selectedRoom,this.rangeStart,this.rangeEnd,"diagnostics","json");Pt(e,t,"application/json"),this._openDropdown=null}_copyCsvToClipboard(){if(!this.data)return;const e=Mt(this.data);e&&(Rt(e),this._openDropdown=null)}_copyDiagnosticsToClipboard(){if(!this.data)return;const e=zt(this.selectedRoom,this.data,this.rooms[this.selectedRoom],this.controlMode);e&&(Rt(e),this._openDropdown=null)}_toggleDropdown(e){this._openDropdown=this._openDropdown===e?null:e}_closeDropdowns(){this._openDropdown&&(this._openDropdown=null)}};Q.styles=D`
    :host {
      display: block;
    }

    .selector-row {
      margin-bottom: 16px;
    }

    .selector-row ha-select {
      width: 100%;
    }

    .range-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      gap: 12px;
    }

    .range-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
    }

    .range-bar {
      display: inline-flex;
      border-radius: 12px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
    }

    .range-bar > :first-child {
      border-radius: 12px 0 0 12px;
    }

    .range-bar > :last-child {
      border-radius: 0 12px 12px 0;
    }

    .range-chip {
      padding: 7px 14px;
      border: none;
      border-right: 1px solid var(--divider-color);
      background: transparent;
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
    }

    .range-chip:last-child {
      border-right: none;
    }

    .range-chip:hover:not([active]) {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
      color: var(--primary-text-color);
    }

    .range-chip[active] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .picker-chip {
      display: flex;
      align-items: center;
      padding: 0;
      cursor: pointer;
    }

    .picker-chip ha-date-range-picker {
      --mdc-icon-size: 18px;
      --mdc-icon-button-size: 32px;
    }

    .picker-chip.picker-active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .date-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .date-label.custom-active {
      color: var(--primary-color);
    }

    .action-buttons {
      display: flex;
      gap: 8px;
    }

    .export-split {
      position: relative;
      display: inline-flex;
    }

    .export-btn {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 7px 14px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-btn:hover {
      color: var(--primary-text-color);
      border-color: var(--primary-color);
    }

    .export-btn[disabled] {
      opacity: 0.4;
      cursor: default;
    }

    .arrow-icon {
      --mdc-icon-size: 14px;
      margin-left: 2px;
      margin-right: -4px;
    }

    .export-dropdown {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 4px;
      min-width: 100%;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      z-index: 10;
      overflow: hidden;
    }

    .export-dropdown button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-dropdown button:hover {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
    }

    .export-dropdown button + button {
      border-top: 1px solid var(--divider-color);
    }

    @media (max-width: 600px) {
      .range-row {
        flex-wrap: wrap;
      }
      .range-controls {
        flex-wrap: wrap;
      }
      .range-chip {
        padding: 6px 10px;
        font-size: 11px;
      }
    }
  `,oe([h({attribute:!1})],Q.prototype,"hass",2),oe([h({attribute:!1})],Q.prototype,"rooms",2),oe([h({type:String})],Q.prototype,"selectedRoom",2),oe([h({type:Number})],Q.prototype,"rangeStart",2),oe([h({type:Number})],Q.prototype,"rangeEnd",2),oe([h({type:String})],Q.prototype,"activeQuick",2),oe([h({attribute:!1})],Q.prototype,"data",2),oe([h({type:String})],Q.prototype,"controlMode",2),oe([h({type:String})],Q.prototype,"language",2),oe([m()],Q.prototype,"_openDropdown",2),Q=oe([R("rs-analytics-toolbar")],Q);const Qi=3*36e5;function Yi(e,t){const{hass:i,language:s,chartAnchor:o,forecast:n}=t,a=C=>O(C,i),d=[],c=[],u=[],_=[];for(const C of e){const v=C.ts*1e3;C.room_temp!==null&&d.push([v,a(C.room_temp)]),C.target_temp!==null&&c.push([v,a(C.target_temp)]),C.predicted_temp!==null&&u.push([v,a(C.predicted_temp)]),C.outdoor_temp!==null&&_.push([v,a(C.outdoor_temp)])}for(const C of n??[]){const v=C.ts*1e3;C.target_temp!==null&&c.push([v,a(C.target_temp)]),C.predicted_temp!==null&&u.push([v,a(C.predicted_temp)])}const g=[{id:"room_temp",type:"line",name:r("analytics.temperature",s),color:"rgb(255, 152, 0)",data:d,showSymbol:!1,smooth:!0,lineStyle:{width:2},yAxisIndex:0},{id:"target_temp",type:"line",name:r("analytics.target",s),color:"rgb(76, 175, 80)",data:c,showSymbol:!1,smooth:!1,lineStyle:{width:2,type:"dashed"},yAxisIndex:0}];u.length>0&&g.push({id:"predicted_temp",type:"line",name:r("analytics.prediction",s),color:"rgb(33, 150, 243)",data:u,showSymbol:!1,smooth:!0,lineStyle:{width:2,type:"dotted"},yAxisIndex:0}),_.length>0&&g.push({id:"outdoor_temp",type:"line",name:r("analytics.outdoor",s),color:"rgb(158, 158, 158)",data:_,showSymbol:!1,smooth:!0,lineStyle:{width:1},yAxisIndex:0});const y=[],S=[],A=[];let M=!1,F=!1,ce=!1;for(const C of e){const v=C.ts*1e3;C.mode==="heating"?(y.push([v,999]),M=!0):y.push([v,null]),C.mode==="cooling"?(S.push([v,999]),F=!0):S.push([v,null]),C.window_open?(A.push([v,999]),ce=!0):A.push([v,null])}return M&&g.push({id:"heating_events",type:"line",name:r("analytics.heating_period",s),color:"rgb(244, 67, 54)",data:y,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(244, 67, 54, 0.08)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1}),F&&g.push({id:"cooling_events",type:"line",name:r("analytics.cooling_period",s),color:"rgb(63, 81, 181)",data:S,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(63, 81, 181, 0.08)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1}),ce&&g.push({id:"window_events",type:"line",name:r("analytics.window_open_period",s),color:"rgb(0, 150, 136)",data:A,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(0, 150, 136, 0.1)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1}),g.push({id:"now_marker",type:"line",name:"",color:"rgba(255,255,255,0.3)",data:[[o,-999],[o,999]],showSymbol:!1,lineStyle:{width:1,type:"dashed"},yAxisIndex:0,tooltip:{show:!1},z:-2}),g}function Ji(e,t,i){const{hass:s,language:o,chartAnchor:n,rangeStart:a,rangeEnd:d}=i,c=f(s),u={type:"value",name:c};if(e.length>0){let g=1/0,y=-1/0;for(const M of e)M<g&&(g=M),M>y&&(y=M);const S=y-g,A=Math.max(S*.1,.5);u.min=Math.floor((g-A)*2)/2,u.max=Math.ceil((y+A)*2)/2}const _=Math.abs(d-Date.now())<36e5;return{xAxis:{type:"time",min:a,max:_?n+Qi:d},yAxis:u,dataZoom:[{type:"inside",xAxisIndex:0,filterMode:"none"}],tooltip:{trigger:"axis",axisPointer:{snap:!1},valueFormatter:g=>g.toFixed(1)+" "+c,formatter:g=>{var ce,C;if(!Array.isArray(g)||g.length===0)return"";let A=`<div style="font-weight:500;margin-bottom:4px">${new Date(g[0].value[0]).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</div>`,M=null,F=null;for(const v of g){if((ce=v.seriesId)!=null&&ce.endsWith("_events"))continue;const w=(C=v.value)==null?void 0:C[1];w!=null&&(A+=`<div>${v.color?`<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${v.color};margin-right:6px"></span>`:""}${v.seriesName}: ${w.toFixed(1)} ${c}</div>`,v.seriesId==="room_temp"&&(M=w),v.seriesId==="predicted_temp"&&(F=w))}if(M!==null&&F!==null){const v=M-F,w=v>=0?"+":"";A+=`<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">Delta: ${w}${v.toFixed(2)} ${c}</div>`}if(t.length>0){const v=g[0].value[0]/1e3;let w=null,j=1/0;for(const N of t){const Y=Math.abs(N.ts-v);Y<j&&(j=Y,w=N)}if(w){const N=[];if(w.mode==="heating"){const Y=w.heating_power;if(Y!=null&&Y>0&&Y<100?N.push(`${r("analytics.heating_period",o)} ${Y}%`):N.push(r("analytics.heating_period",o)),Y!=null&&Y>0&&w.room_temp!=null){const Ye=Math.round((w.room_temp+Y/100*(30-w.room_temp))*10)/10;N.push(`TRV ${P(Ye,s)} ${c}`)}}else w.mode==="cooling"&&N.push(r("analytics.cooling_period",o));w.window_open&&N.push(r("analytics.window_open_period",o)),N.length>0&&(A+=`<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;color:rgba(255,255,255,0.7)">${N.join(" · ")}</div>`)}}return A}},grid:{top:15,left:10,right:10,bottom:5,containLabel:!0}}}var Xi=Object.defineProperty,es=Object.getOwnPropertyDescriptor,ge=(e,t,i,s)=>{for(var o=s>1?void 0:s?es(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&Xi(t,i,o),o};let ne=class extends z{constructor(){super(...arguments),this.data=null,this.rangeStart=0,this.rangeEnd=0,this.chartAnchor=0,this.language="en",this._hiddenSeries=new Set(["outdoor_temp"]),this._chartInfoExpanded=!1}render(){var c,u;const e=this.language,t=this.data?[...this.data.history,...this.data.detail]:[],i=[...t,...((c=this.data)==null?void 0:c.forecast)??[]],s={hass:this.hass,language:e,chartAnchor:this.chartAnchor,rangeStart:this.rangeStart,rangeEnd:this.rangeEnd,forecast:(u=this.data)==null?void 0:u.forecast},o=t.length>0?Yi(t,s):[],n=[],a=o.map(_=>{const g=_.id,y=_.lineStyle||{},S=g.endsWith("_events");if(this._hiddenSeries.has(g)){const M={..._,lineStyle:{...y,width:0,opacity:0}};return _.areaStyle&&(M.areaStyle={..._.areaStyle,opacity:0}),M}if(!S&&g!=="now_marker")for(const M of _.data)M&&M[1]!=null&&n.push(M[1]);const A={..._,lineStyle:{...y,opacity:1}};return _.areaStyle&&(A.areaStyle={..._.areaStyle,opacity:1}),A}),d=Ji(n,i,s);return l`
      <ha-card>
        <div class="card-header">
          <span>${r("analytics.temperature",e)}</span>
          <ha-icon
            class="info-icon chart-info-toggle ${this._chartInfoExpanded?"info-active":""}"
            icon="mdi:information-outline"
            @click=${()=>{this._chartInfoExpanded=!this._chartInfoExpanded}}
          ></ha-icon>
        </div>
        ${this._chartInfoExpanded?l`<div class="chart-info-panel">
              ${this._renderMarkdown(r("analytics.chart_info_body",e))}
            </div>`:p}
        ${t.length>0?l`
              <ha-chart-base
                .hass=${this.hass}
                .data=${a}
                .options=${d}
                .height=${"300px"}
                style="height: 300px"
              ></ha-chart-base>
              ${this._renderSeriesLegend(o)}
            `:l`<div class="chart-empty">
              <ha-icon icon="mdi:chart-line"></ha-icon>
              <span>${r("analytics.no_data",e)}</span>
            </div>`}
      </ha-card>
    `}_renderSeriesLegend(e){const t=e.filter(i=>i.id!=="now_marker");return l`
      <div class="series-legend">
        ${t.map(i=>{const s=i.id,o=this._hiddenSeries.has(s);return l`
            <button
              class="legend-item ${o?"legend-hidden":""}"
              @click=${()=>this._toggleSeries(s)}
            >
              <span class="legend-dot" style="background: ${i.color}"></span>
              ${i.name}
            </button>
          `})}
      </div>
    `}_renderMarkdown(e){return e.split(`

`).map(i=>l`<p>
          ${i.split(/(\*\*.*?\*\*)/).map(s=>s.startsWith("**")&&s.endsWith("**")?l`<strong>${s.slice(2,-2)}</strong>`:s)}
        </p>`)}_toggleSeries(e){const t=new Set(this._hiddenSeries);t.has(e)?t.delete(e):t.add(e),this._hiddenSeries=t}};ne.styles=[lt,D`
      :host {
        display: block;
      }

      ha-card {
        margin-bottom: 16px;
      }

      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 16px 0;
        font-size: 16px;
        font-weight: 500;
      }

      .chart-info-toggle {
        --mdc-icon-size: 20px;
      }

      .chart-info-panel {
        margin: 8px 16px 4px;
        padding: 12px 14px;
        border-radius: 8px;
        background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
        font-size: 13px;
        line-height: 1.6;
        color: var(--secondary-text-color);
      }

      .chart-info-panel p {
        margin: 0 0 8px;
      }

      .chart-info-panel p:last-child {
        margin-bottom: 0;
      }

      .chart-info-panel strong {
        color: var(--primary-text-color);
      }

      .series-legend {
        display: flex;
        justify-content: center;
        gap: 6px;
        padding: 8px 16px 12px;
        flex-wrap: wrap;
      }

      .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border: none;
        border-radius: 12px;
        background: transparent;
        color: var(--primary-text-color);
        font-size: 12px;
        font-family: inherit;
        cursor: pointer;
        transition: opacity 0.2s;
      }

      .legend-item:hover {
        background: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
      }

      .legend-item.legend-hidden {
        opacity: 0.35;
      }

      .legend-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
      }

      .chart-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 200px;
        gap: 8px;
        color: var(--secondary-text-color);
        opacity: 0.5;
        --mdc-icon-size: 40px;
        font-size: 13px;
      }
    `],ge([h({attribute:!1})],ne.prototype,"hass",2),ge([h({attribute:!1})],ne.prototype,"data",2),ge([h({type:Number})],ne.prototype,"rangeStart",2),ge([h({type:Number})],ne.prototype,"rangeEnd",2),ge([h({type:Number})],ne.prototype,"chartAnchor",2),ge([h({type:String})],ne.prototype,"language",2),ge([m()],ne.prototype,"_hiddenSeries",2),ge([m()],ne.prototype,"_chartInfoExpanded",2),ne=ge([R("rs-analytics-chart")],ne);var ts=Object.defineProperty,is=Object.getOwnPropertyDescriptor,Fe=(e,t,i,s)=>{for(var o=s>1?void 0:s?is(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&ts(t,i,o),o};let Te=class extends z{constructor(){super(...arguments),this.data=null,this.language="en",this._expandedStat=null}render(){var Y,Ye,Lt;const e=this.language,t=!!((Ye=(Y=this.data)==null?void 0:Y.model)!=null&&Ye.model),i=(Lt=this.data)==null?void 0:Lt.model,s=i==null?void 0:i.model,o=(i==null?void 0:i.confidence)??0,n=(i==null?void 0:i.n_samples)??0,a=(i==null?void 0:i.n_heating)??0,d=(i==null?void 0:i.n_cooling)??0,c=(i==null?void 0:i.applicable_modes)??[],u=i==null?void 0:i.prediction_std_idle,_=i==null?void 0:i.prediction_std_heating,g=(i==null?void 0:i.mpc_active)??!1,y=Math.round(o*100),S=new Set(c),A=S.has("heating"),M=S.has("cooling"),F=a>=10,ce=d>=10,C=n-a-d>=10,v=(i==null?void 0:i.n_observations)??n,w="—",j=[],N=(_e,Nt,It,ms,hs)=>{j.push({id:_e,labelKey:It,infoKey:hs});const Wt=this._expandedStat===_e;return l`
        <div class="model-stat ${Wt?"active":""}" @click=${()=>this._toggleStat(_e)}>
          <div class="stat-content">
            <span class="model-value ${Nt===w?"pending":""}">${Nt}</span>
            <span class="model-label">${r(It,e)}${""}</span>
          </div>
          <ha-icon
            class="info-icon ${Wt?"info-active":""}"
            icon="mdi:information-outline"
          ></ha-icon>
        </div>
      `};return l`
      <ha-card>
        <div class="card-header">
          <span>${r("analytics.model_status",e)}</span>
        </div>
        <div class="card-content">
          <div class="confidence-hero">
            <div class="confidence-top">
              <div class="confidence-main">
                <span class="confidence-value">${t?y+"%":"0%"}</span>
                <span class="confidence-label">
                  ${r("analytics.confidence",e)}
                  <ha-icon
                    class="info-icon ${this._expandedStat==="confidence"?"info-active":""}"
                    icon="mdi:information-outline"
                    @click=${()=>this._toggleStat("confidence")}
                  ></ha-icon>
                </span>
              </div>
              <div class="confidence-meta">
                <span class="meta-value">${t?v:0}</span>
                <span class="meta-label">
                  ${r("analytics.data_points",e)}
                  <ha-icon
                    class="info-icon ${this._expandedStat==="data_points"?"info-active":""}"
                    icon="mdi:information-outline"
                    @click=${()=>this._toggleStat("data_points")}
                  ></ha-icon>
                </span>
              </div>
            </div>
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${t?y:0}%"></div>
            </div>
            <div class="control-mode-badge ${g?"mpc":"bangbang"}">
              <ha-icon icon=${g?"mdi:brain":"mdi:school-outline"}></ha-icon>
              ${r(g?"analytics.control_mode_mpc":"analytics.control_mode_bangbang",e)}
            </div>
            ${this._expandedStat==="confidence"?l`<div class="info-panel stat-info-panel">
                  <strong>${r("analytics.confidence",e)}</strong>
                  ${r("analytics.info.confidence",e)}
                </div>`:p}
            ${this._expandedStat==="data_points"?l`<div class="info-panel stat-info-panel">
                  <strong>${r("analytics.data_points",e)}</strong>
                  ${r("analytics.info.data_points",e)}
                </div>`:p}
          </div>

          <div class="model-grid">
            ${N("time_constant",C&&s&&s.U>0?(1/s.U).toFixed(1)+"h":w,"analytics.time_constant","","analytics.info.time_constant")}
            ${A?N("heating_rate",F&&s?ae(s.Q_heat,this.hass).toFixed(1)+f(this.hass)+"/h":w,"analytics.heating_rate","","analytics.info.heating_rate"):p}
            ${M?N("cooling_rate",ce&&s?ae(s.Q_cool,this.hass).toFixed(1)+f(this.hass)+"/h":w,"analytics.cooling_rate","","analytics.info.cooling_rate"):p}
            ${s&&s.Q_solar>.1?N("solar_gain",ae(s.Q_solar,this.hass).toFixed(1)+f(this.hass)+"/h","analytics.solar_gain","","analytics.info.solar_gain"):p}
            ${N("accuracy_idle",C&&u!=null?"±"+ae(u,this.hass).toFixed(2)+f(this.hass):w,"analytics.accuracy_idle","","analytics.info.accuracy_idle")}
            ${A?N("accuracy_heating",F&&_!=null?"±"+ae(_,this.hass).toFixed(2)+f(this.hass):w,"analytics.accuracy_heating","","analytics.info.accuracy_heating"):p}
          </div>
          ${this._expandedStat&&j.find(_e=>_e.id===this._expandedStat)?l`<div class="info-panel stat-info-panel">
                <strong>${r(j.find(_e=>_e.id===this._expandedStat).labelKey,e)}</strong>
                ${r(j.find(_e=>_e.id===this._expandedStat).infoKey,e)}
              </div>`:p}

        </div>
      </ha-card>
    `}_toggleStat(e){this._expandedStat=this._expandedStat===e?null:e}};Te.styles=[lt,D`
      :host {
        display: block;
      }

      ha-card {
        margin-bottom: 16px;
      }

      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 16px 0;
        font-size: 16px;
        font-weight: 500;
      }

      .card-content {
        padding: 16px;
      }

      .confidence-hero {
        margin-bottom: 16px;
      }

      .confidence-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        margin-bottom: 8px;
      }

      .confidence-main {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .confidence-value {
        font-size: 28px;
        font-weight: 600;
        color: var(--primary-text-color);
      }

      .confidence-label {
        font-size: 13px;
        color: var(--secondary-text-color);
      }

      .confidence-meta {
        display: flex;
        align-items: baseline;
        gap: 6px;
      }

      .meta-value {
        font-size: 16px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .meta-label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .control-mode-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-top: 8px;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        --mdc-icon-size: 14px;
      }

      .control-mode-badge.mpc {
        background: rgba(76, 175, 80, 0.12);
        color: var(--success-color, #4caf50);
      }

      .control-mode-badge.bangbang {
        background: rgba(158, 158, 158, 0.12);
        color: var(--secondary-text-color);
      }

      .confidence-bar {
        height: 4px;
        border-radius: 2px;
        background: var(--divider-color);
        overflow: hidden;
      }

      .confidence-fill {
        height: 100%;
        border-radius: 2px;
        background: var(--primary-color);
        transition: width 0.6s ease;
      }

      .model-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 12px;
      }

      .model-stat {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--divider-color);
        cursor: pointer;
        transition: border-color 0.2s;
      }

      .model-stat.active {
        border-color: var(--primary-color);
      }

      .stat-content {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .model-value {
        font-size: 18px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .model-value.pending {
        opacity: 0.2;
      }

      .model-label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .info-panel.stat-info-panel {
        margin-top: 12px;
      }

      @media (max-width: 600px) {
        .model-grid {
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }
      }
    `],Fe([h({attribute:!1})],Te.prototype,"hass",2),Fe([h({attribute:!1})],Te.prototype,"data",2),Fe([h({type:String})],Te.prototype,"language",2),Fe([m()],Te.prototype,"_expandedStat",2),Te=Fe([R("rs-analytics-model")],Te);var ss=Object.defineProperty,os=Object.getOwnPropertyDescriptor,X=(e,t,i,s)=>{for(var o=s>1?void 0:s?os(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&ss(t,i,o),o};let V=class extends z{constructor(){super(...arguments),this.rooms={},this.initialRoom="",this.controlMode="bangbang",this._selectedRoom="",this._rangeStart=new Date(new Date().setHours(0,0,0,0)).getTime(),this._rangeEnd=Date.now(),this._data=null,this._chartAnchor=Date.now(),this._loading=!1,this._activeQuick="24h"}connectedCallback(){super.connectedCallback(),this._refreshInterval=setInterval(()=>this._silentRefresh(),6e4)}disconnectedCallback(){super.disconnectedCallback(),this._refreshInterval&&(clearInterval(this._refreshInterval),this._refreshInterval=void 0)}willUpdate(e){e.has("initialRoom")&&this.initialRoom&&(this._selectedRoom=this.initialRoom);let t=!1;if(e.has("rooms")&&!this._selectedRoom){const i=Object.keys(this.rooms);i.length>0&&(this._selectedRoom=i[0],t=!0,this.dispatchEvent(new CustomEvent("room-selected",{detail:{areaId:i[0]},bubbles:!0,composed:!0})))}(t||e.has("_selectedRoom")||e.has("_rangeStart")||e.has("_rangeEnd"))&&this._selectedRoom&&this._fetchData()}render(){const e=this.hass.language;return l`
      <rs-analytics-toolbar
        .hass=${this.hass}
        .rooms=${this.rooms}
        .selectedRoom=${this._selectedRoom}
        .rangeStart=${this._rangeStart}
        .rangeEnd=${this._rangeEnd}
        .activeQuick=${this._activeQuick}
        .data=${this._data}
        .controlMode=${this.controlMode}
        .language=${e}
        @room-selected=${this._onRoomSelected}
        @range-changed=${this._onRangeChanged}
      ></rs-analytics-toolbar>
      ${this._selectedRoom?this._loading?l`<div class="loading">${r("panel.loading",e)}</div>`:l`
              <rs-analytics-chart
                .hass=${this.hass}
                .data=${this._data}
                .rangeStart=${this._rangeStart}
                .rangeEnd=${this._rangeEnd}
                .chartAnchor=${this._chartAnchor}
                .language=${e}
              ></rs-analytics-chart>
              <rs-analytics-model
                .hass=${this.hass}
                .data=${this._data}
                .language=${e}
              ></rs-analytics-model>
            `:l`
            <div class="no-data">
              <ha-icon icon="mdi:chart-line" style="--mdc-icon-size: 48px; opacity: 0.4"></ha-icon>
              <p>${r("analytics.select_room",e)}</p>
            </div>
          `}
    `}_onRoomSelected(e){const t=e.detail.areaId;t&&t!==this._selectedRoom&&(this._selectedRoom=t,this.dispatchEvent(new CustomEvent("room-selected",{detail:{areaId:t},bubbles:!0,composed:!0})))}_onRangeChanged(e){const{activeQuick:t,rangeStart:i,rangeEnd:s,chartAnchor:o}=e.detail;this._activeQuick=t,this._rangeStart=i,this._rangeEnd=s,this._chartAnchor=o}_buildWsParams(){return{type:"roommind/analytics/get",area_id:this._selectedRoom,start_ts:this._rangeStart/1e3,end_ts:this._rangeEnd/1e3}}async _fetchData(){if(this._selectedRoom){this._loading=!0,this._data=null,this._chartAnchor=this._rangeEnd;try{const e=await this.hass.callWS(this._buildWsParams());this._data=e}catch(e){console.debug("[RoomMind] fetchData:",e),this._data=null}finally{this._loading=!1}}}async _silentRefresh(){if(!(!this._selectedRoom||this._loading))try{const e=await this.hass.callWS(this._buildWsParams());this._data=e,this._chartAnchor=Date.now()}catch(e){console.debug("[RoomMind] silentRefresh:",e)}}};V.styles=D`
    :host {
      display: block;
    }

    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .no-data p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
      margin-top: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }
  `,X([h({attribute:!1})],V.prototype,"hass",2),X([h({type:Object})],V.prototype,"rooms",2),X([h()],V.prototype,"initialRoom",2),X([h()],V.prototype,"controlMode",2),X([m()],V.prototype,"_selectedRoom",2),X([m()],V.prototype,"_rangeStart",2),X([m()],V.prototype,"_rangeEnd",2),X([m()],V.prototype,"_data",2),X([m()],V.prototype,"_chartAnchor",2),X([m()],V.prototype,"_loading",2),X([m()],V.prototype,"_activeQuick",2),V=X([R("rs-analytics")],V);var ns=Object.defineProperty,as=Object.getOwnPropertyDescriptor,T=(e,t,i,s)=>{for(var o=s>1?void 0:s?as(t,i):t,n=e.length-1,a;n>=0;n--)(a=e[n])&&(o=(s?a(t,i,o):a(o))||o);return s&&o&&ns(t,i,o),o};const rs="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",ls="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",cs="M16,11.78L20.24,4.45L21.97,5.45L16.74,14.5L10.23,10.75L5.46,19H22V21H2V3H4V17.54L9.5,8L16,11.78Z",ds="M15 13V5A3 3 0 0 0 9 5V13A5 5 0 1 0 15 13M12 4A1 1 0 0 1 13 5V8H11V5A1 1 0 0 1 12 4Z";let E=class extends z{constructor(){super(...arguments),this.narrow=!1,this.route={path:""},this.panel={},this._activeTab="areas",this._rooms={},this._roomsLoaded=!1,this._selectedAreaId=null,this._analyticsRoom="",this._vacationActive=!1,this._vacationTemp=null,this._vacationUntil=null,this._hiddenRooms=[],this._showHiddenRooms=!1,this._controlMode="bangbang",this._climateControlActive=!0,this._presenceEnabled=!1,this._anyoneHome=!0,this._presencePersons=[],this._presenceAwayAction="eco",this._saveStatus="idle",this._roomOrder=[],this._groupByFloor=!1,this._reorderMode=!1,this._elementsLoaded=!1,this._routeApplied=!1,this._areaInfosCache=[],this._onSaveStatus=e=>{e.stopPropagation(),this._saveStatusTimeout&&clearTimeout(this._saveStatusTimeout),this._saveStatus=e.detail.status,e.detail.status==="saved"&&(this._saveStatusTimeout=setTimeout(()=>{this._saveStatus="idle"},2e3))}}connectedCallback(){super.connectedCallback(),Hi().then(()=>{this._elementsLoaded=!0}),this._loadRooms(),this._refreshInterval=setInterval(()=>this._loadRooms(),5e3),this.addEventListener("save-status",this._onSaveStatus),this._routeApplied||(this._applyRoute(),this._routeApplied=!0)}disconnectedCallback(){super.disconnectedCallback(),this._refreshInterval&&(clearInterval(this._refreshInterval),this._refreshInterval=void 0),this._saveStatusTimeout&&clearTimeout(this._saveStatusTimeout),this.removeEventListener("save-status",this._onSaveStatus)}render(){var o,n,a;if(!this._elementsLoaded)return l``;const e=this.hass.language,t=!!this._selectedAreaId,i=t?(n=(o=this.hass)==null?void 0:o.areas)==null?void 0:n[this._selectedAreaId]:null,s={areas:r("panel.tab.rooms",e),analytics:r("tabs.analytics",e),settings:r("panel.tab.settings",e)};return l`
      <div class="toolbar">
        ${t?l`<ha-icon-button
              .path=${rs}
              @click=${this._onBackFromDetail}
            ></ha-icon-button>`:l`<ha-menu-button
              .hass=${this.hass}
              .narrow=${this.narrow}
            ></ha-menu-button>`}
        <div class="title">
          ${t?((a=this._rooms[this._selectedAreaId])==null?void 0:a.display_name)||(i==null?void 0:i.name)||"":r("panel.title",e)}
        </div>
        ${this._renderSaveIndicator()}
        ${t&&this._rooms[this._selectedAreaId]?l`<ha-icon-button
              .path=${cs}
              @click=${this._onGoToAnalytics}
            ></ha-icon-button><ha-icon-button
              .path=${ls}
              @click=${this._onDeleteRoom}
            ></ha-icon-button>`:p}
        ${!t&&this._activeTab==="analytics"&&this._analyticsRoom?l`<ha-icon-button
              .path=${ds}
              @click=${this._onGoToRoomFromAnalytics}
            ></ha-icon-button>`:p}
      </div>

      ${t?p:l`
            <div class="tabs">
              ${Object.keys(s).map(d=>l`
                  <button
                    class="tab"
                    ?active=${this._activeTab===d}
                    @click=${()=>this._onTabClicked(d)}
                  >
                    ${s[d]}
                  </button>
                `)}
            </div>
          `}

      <div class="content">${this._renderTab()}</div>
    `}_renderTab(){switch(this._activeTab){case"areas":return this._renderAreas();case"analytics":return l`<rs-analytics
          .hass=${this.hass}
          .rooms=${this._rooms}
          .initialRoom=${this._analyticsRoom}
          .controlMode=${this._controlMode}
          @room-selected=${this._onAnalyticsRoomSelected}
        ></rs-analytics>`;case"settings":return this._renderSettings();default:return p}}_renderAreas(){var d,c;if(this._selectedAreaId){const u=(c=(d=this.hass)==null?void 0:d.areas)==null?void 0:c[this._selectedAreaId];if(u){const _=this._rooms[this._selectedAreaId]??null;return l`
          <rs-room-detail
            .area=${u}
            .config=${_}
            .hass=${this.hass}
            .presenceEnabled=${this._presenceEnabled}
            .presencePersons=${this._presencePersons}
            .climateControlActive=${this._climateControlActive}
            @back-clicked=${this._onBackFromDetail}
            @room-updated=${this._onRoomUpdated}
          ></rs-room-detail>
        `}this._selectedAreaId=null}if(!this._roomsLoaded)return l`<div class="loading">${r("panel.loading",this.hass.language)}</div>`;const e=this._areaInfosCache,t=e.filter(u=>!this._hiddenRooms.includes(u.area.area_id)),i=e.filter(u=>this._hiddenRooms.includes(u.area.area_id));if(e.length===0)return l`
        <div class="placeholder">
          <ha-icon icon="mdi:home" style="--mdc-icon-size: 56px; opacity: 0.4"></ha-icon>
          <p>${r("panel.no_areas",this.hass.language)}<br/>${r("panel.no_areas_hint",this.hass.language)}</p>
        </div>
      `;const s=t.filter(u=>u.config).length,o=t.filter(u=>{var _,g;return((g=(_=u.config)==null?void 0:_.live)==null?void 0:g.mode)==="heating"}).length,n=t.filter(u=>{var _,g;return((g=(_=u.config)==null?void 0:_.live)==null?void 0:g.mode)==="cooling"}).length,a=this.hass.language;return l`
      ${s>0||i.length>0?l`
            <ha-card class="stats-bar">
              ${s>0?l`
                <div class="stat">
                  <span class="stat-value">${s}</span>
                  <span class="stat-label">${r("panel.stat.rooms",a)}</span>
                </div>
                <div class="stat">
                  <span class="stat-value" style="color: var(--warning-color, #ff9800)">${o}</span>
                  <span class="stat-label">${r("panel.stat.heating",a)}</span>
                </div>
                <div class="stat">
                  <span class="stat-value" style="color: var(--info-color, #2196f3)">${n}</span>
                  <span class="stat-label">${r("panel.stat.cooling",a)}</span>
                </div>
              `:p}
              <span class="stats-actions">
                ${i.length>0?l`<ha-icon-button
                      class="hidden-rooms-toggle"
                      .path=${Tt}
                      @click=${()=>{this._showHiddenRooms=!this._showHiddenRooms}}
                    ></ha-icon-button>`:p}
                ${this._reorderMode?l`<ha-button class="reorder-done" @click=${this._onReorderDone}>
                      ${r("panel.reorder_done",a)}
                    </ha-button>`:l`<ha-icon-button
                      class="reorder-btn"
                      .path=${"M9,3L5,7H8V14H10V7H13M16,17V10H14V17H11L15,21L19,17H16Z"}
                      @click=${()=>{this._reorderMode=!0}}
                      title=${r("panel.reorder",a)}
                    ></ha-icon-button>`}
              </span>
            </ha-card>
          `:p}

      ${this._showHiddenRooms&&i.length>0?l`
            <ha-card class="hidden-rooms-panel">
              <div class="hidden-rooms-header">
                <span>${r("panel.hidden_rooms",a)} (${i.length})</span>
              </div>
              ${i.map(u=>l`
                <div class="hidden-room-row">
                  <span class="hidden-room-name">${u.area.name}</span>
                  <ha-button @click=${()=>this._unhideRoom(u.area.area_id)}>
                    ${r("panel.unhide",a)}
                  </ha-button>
                </div>
              `)}
            </ha-card>
          `:p}

      ${this._vacationActive&&this._vacationTemp!==null?l`
            <ha-card class="vacation-banner">
              <div class="vacation-content">
                <ha-icon icon="mdi:airplane"></ha-icon>
                <div class="vacation-text">
                  <span class="vacation-title">${r("vacation.banner_title",this.hass.language)}</span>
                  <span class="vacation-detail">${r("vacation.banner_detail",this.hass.language,{temp:P(this._vacationTemp,this.hass),unit:f(this.hass),date:this._vacationUntil?new Date(this._vacationUntil*1e3).toLocaleString(this.hass.language,{dateStyle:"medium",timeStyle:"short"}):"—"})}</span>
                </div>
                <ha-button @click=${this._clearVacation}>
                  ${r("vacation.deactivate",this.hass.language)}
                </ha-button>
              </div>
            </ha-card>
          `:p}

      ${this._presenceEnabled&&!this._anyoneHome?l`
            <ha-card class="presence-banner">
              <div class="vacation-content">
                <ha-icon icon="mdi:home-off-outline"></ha-icon>
                <div class="vacation-text">
                  <span class="vacation-title">${r("presence.banner_title",this.hass.language)}</span>
                  <span class="vacation-detail">${r(this._presenceAwayAction==="off"?"presence.banner_detail_off":"presence.banner_detail",this.hass.language)}</span>
                </div>
              </div>
            </ha-card>
          `:p}

      ${this._getFloorGroups(t).map(u=>l`
        ${u.name?l`<h4 class="floor-heading">${u.name}</h4>`:p}
        <div class="area-grid">
          ${u.items.map((_,g)=>l`
              <rs-area-card
                .area=${_.area}
                .config=${_.config}
                .climateEntityCount=${_.climateEntityCount}
                .tempSensorCount=${_.tempSensorCount}
                .hass=${this.hass}
                .controlMode=${this._controlMode}
                .climateControlActive=${this._climateControlActive}
                .reordering=${this._reorderMode}
                .canMoveUp=${g>0}
                .canMoveDown=${g<u.items.length-1}
                @area-selected=${this._onAreaSelected}
                @hide-room=${this._onHideRoom}
                @move-room-up=${this._onMoveRoomUp}
                @move-room-down=${this._onMoveRoomDown}
              ></rs-area-card>
            `)}
        </div>
      `)}
    `}_renderSettings(){return l`<rs-settings .hass=${this.hass} .rooms=${this._rooms}></rs-settings>`}_computeAreaInfos(){var s;if(!((s=this.hass)!=null&&s.areas))return[];const t=Object.values(this.hass.areas).map(o=>{const n=Ct(o.area_id,this.hass.entities,this.hass.devices),a=n.filter(c=>c.entity_id.startsWith("climate.")).length,d=n.filter(c=>{var u,_;return c.entity_id.startsWith("sensor.")&&((_=(u=this.hass.states[c.entity_id])==null?void 0:u.attributes)==null?void 0:_.device_class)==="temperature"}).length;return{area:o,config:this._rooms[o.area_id]??null,climateEntityCount:a,tempSensorCount:d}}),i=new Map(this._roomOrder.map((o,n)=>[o,n]));return t.sort((o,n)=>{const a=i.get(o.area.area_id),d=i.get(n.area.area_id);if(a!==void 0&&d!==void 0)return a-d;if(a!==void 0)return-1;if(d!==void 0)return 1;const c=o.config?2:o.climateEntityCount>0?1:0,u=n.config?2:n.climateEntityCount>0?1:0;return c!==u?u-c:o.area.name.localeCompare(n.area.name)}),t}_getFloorGroups(e){if(!this._groupByFloor||!this.hass.floors)return[{name:"",items:e}];const t=this.hass.floors,i=this.hass.language,s=new Map,o=[];for(const n of e){const a=n.area.floor_id??null;s.has(a)||(s.set(a,[]),o.push(a)),s.get(a).push(n)}return o.sort((n,a)=>{if(n===null)return 1;if(a===null)return-1;const d=t[n],c=t[a];return(d==null?void 0:d.level)!=null&&(c==null?void 0:c.level)!=null?c.level-d.level:(d==null?void 0:d.level)!=null?-1:(c==null?void 0:c.level)!=null?1:((d==null?void 0:d.name)??"").localeCompare((c==null?void 0:c.name)??"")}),o.map(n=>{var a;return{name:n===null?r("panel.floor_other",i):((a=t[n])==null?void 0:a.name)??r("panel.floor_other",i),items:s.get(n)}})}async _loadRooms(){try{const e=await this.hass.callWS({type:"roommind/rooms/list"});this._rooms=e.rooms,this._vacationActive=e.vacation_active??!1,this._vacationTemp=e.vacation_temp??null,this._vacationUntil=e.vacation_until??null,this._hiddenRooms=e.hidden_rooms??[],this._roomOrder=e.room_order??[],this._groupByFloor=e.group_by_floor??!1,this._controlMode=e.control_mode??"bangbang",this._climateControlActive=e.climate_control_active??!0,this._presenceEnabled=e.presence_enabled??!1,this._anyoneHome=e.anyone_home??!0,this._presencePersons=e.presence_persons??[],this._presenceAwayAction=e.presence_away_action??"eco"}catch(e){console.debug("[RoomMind] loadRooms:",e)}finally{this._roomsLoaded=!0}}_onBackFromDetail(){this._selectedAreaId=null,this._navigate("")}async _onDeleteRoom(){var t,i;if(!this._selectedAreaId)return;const e=(i=(t=this.hass)==null?void 0:t.areas)==null?void 0:i[this._selectedAreaId];if(e&&confirm(r("room.confirm_delete",this.hass.language,{name:e.name})))try{await this.hass.callWS({type:"roommind/rooms/delete",area_id:this._selectedAreaId}),this._selectedAreaId=null,this._navigate(""),this._loadRooms()}catch(s){console.debug("[RoomMind] deleteRoom:",s)}}_onTabClicked(e){this._activeTab=e,this._selectedAreaId=null,e==="areas"?this._navigate(""):this._navigate(`/${e}`)}_onAreaSelected(e){this._selectedAreaId=e.detail.areaId,this._navigate(`/room/${e.detail.areaId}`)}async _onHideRoom(e){const t=[...new Set([...this._hiddenRooms,e.detail.areaId])];this._hiddenRooms=t;try{await this.hass.callWS({type:"roommind/settings/save",hidden_rooms:t})}catch(i){console.debug("[RoomMind] hideRoom:",i)}}async _unhideRoom(e){const t=this._hiddenRooms.filter(i=>i!==e);this._hiddenRooms=t,t.length===0&&(this._showHiddenRooms=!1);try{await this.hass.callWS({type:"roommind/settings/save",hidden_rooms:t})}catch(i){console.debug("[RoomMind] unhideRoom:",i)}}_onGoToAnalytics(){this._selectedAreaId&&(this._analyticsRoom=this._selectedAreaId,this._selectedAreaId=null,this._activeTab="analytics",this._navigate(`/analytics/${this._analyticsRoom}`))}_onGoToRoomFromAnalytics(){this._analyticsRoom&&(this._selectedAreaId=this._analyticsRoom,this._activeTab="areas",this._navigate(`/room/${this._analyticsRoom}`))}_onAnalyticsRoomSelected(e){this._analyticsRoom=e.detail.areaId,this._navigate(`/analytics/${e.detail.areaId}`)}async _onMoveRoomUp(e){this._moveRoom(e.detail.areaId,-1)}async _onMoveRoomDown(e){this._moveRoom(e.detail.areaId,1)}async _moveRoom(e,t){const i=this._areaInfosCache.filter(s=>!this._hiddenRooms.includes(s.area.area_id));if(this._groupByFloor&&this.hass.floors){const s=this._getFloorGroups(i);for(const o of s){const n=o.items.map(u=>u.area.area_id),a=n.indexOf(e);if(a===-1)continue;const d=a+t;if(d<0||d>=n.length)return;[n[a],n[d]]=[n[d],n[a]];const c=s.flatMap(u=>u===o?n:u.items.map(_=>_.area.area_id));await this._saveRoomOrder(c);return}}else{const s=i.map(a=>a.area.area_id),o=s.indexOf(e);if(o===-1)return;const n=o+t;if(n<0||n>=s.length)return;[s[o],s[n]]=[s[n],s[o]],await this._saveRoomOrder(s)}}async _saveRoomOrder(e){this._roomOrder=e,this._areaInfosCache=this._computeAreaInfos();try{await this.hass.callWS({type:"roommind/settings/save",room_order:e})}catch(t){console.debug("[RoomMind] saveRoomOrder:",t)}}_onReorderDone(){this._reorderMode=!1}async _clearVacation(){try{await this.hass.callWS({type:"roommind/settings/save",vacation_until:null}),this._vacationActive=!1,this._vacationTemp=null,this._vacationUntil=null}catch(e){console.debug("[RoomMind] clearVacation:",e)}}_onRoomUpdated(){this._loadRooms()}_renderSaveIndicator(){if(this._saveStatus==="idle")return p;const e=this.hass.language,t=this._saveStatus==="saving"?"mdi:content-save-outline":this._saveStatus==="saved"?"mdi:check":"mdi:alert-circle-outline",i=this._saveStatus==="saving"?r("settings.saving",e):this._saveStatus==="saved"?r("settings.saved",e):r("settings.error",e);return l`
      <span class="save-indicator ${this._saveStatus}">
        <ha-icon .icon=${t}></ha-icon>
        ${i}
      </span>
    `}willUpdate(e){e.has("route")&&this._routeApplied&&this._applyRoute(),(e.has("_rooms")||e.has("hass"))&&(this._areaInfosCache=this._computeAreaInfos())}updated(e){e.has("hass")&&this.hass&&!this._roomsLoaded&&this._loadRooms()}_navigate(e){history.replaceState(null,"",`/roommind${e}`),window.dispatchEvent(new Event("location-changed"))}_applyRoute(){var t;const e=((t=this.route)==null?void 0:t.path)??"";e.startsWith("/room/")?(this._activeTab="areas",this._selectedAreaId=decodeURIComponent(e.slice(6))):e.startsWith("/analytics/")?(this._activeTab="analytics",this._selectedAreaId=null,this._analyticsRoom=decodeURIComponent(e.slice(11))):e==="/analytics"?(this._activeTab="analytics",this._selectedAreaId=null,this._analyticsRoom=""):e==="/settings"?(this._activeTab="settings",this._selectedAreaId=null):(this._activeTab="areas",this._selectedAreaId=null)}};E.styles=D`
    :host {
      display: block;
      font-family: var(--primary-font-family, Roboto, sans-serif);
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100vh;
    }

    .toolbar {
      display: flex;
      align-items: center;
      height: 56px;
      padding: 0 12px;
      font-size: 20px;
      background-color: var(--app-header-background-color, var(--primary-background-color));
      color: var(--app-header-text-color, var(--primary-text-color));
      border-bottom: 1px solid var(--divider-color);
      box-sizing: border-box;
      position: sticky;
      top: 0;
      z-index: 4;
    }

    .toolbar .title {
      margin-left: 4px;
      font-weight: 400;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .toolbar ha-icon-button {
      color: var(--app-header-text-color, var(--primary-text-color));
    }

    .save-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 400;
      margin-right: 8px;
      opacity: 1;
      transition: opacity 0.3s ease;
    }

    .save-indicator.fade-out {
      opacity: 0;
    }

    .save-indicator ha-icon {
      --mdc-icon-size: 18px;
    }

    .save-indicator.saving {
      color: var(--primary-color, #03a9f4);
    }

    .save-indicator.saved {
      color: var(--success-color, #4caf50);
    }

    .save-indicator.error {
      color: var(--error-color, #d32f2f);
    }

    .tabs {
      display: flex;
      gap: 0;
      border-bottom: 1px solid var(--divider-color);
      padding: 0 16px;
      background: var(--primary-background-color);
      position: sticky;
      top: 56px;
      z-index: 3;
    }

    .tab {
      padding: 12px 24px;
      cursor: pointer;
      border: none;
      background: none;
      color: var(--secondary-text-color);
      font-size: 14px;
      font-weight: 500;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
      font-family: inherit;
    }

    .tab:hover {
      color: var(--primary-text-color);
    }

    .tab[active] {
      color: var(--primary-color);
      border-bottom-color: var(--primary-color);
    }

    .content {
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
      box-sizing: border-box;
    }

    @media (max-width: 600px) {
      .content {
        padding: 16px;
      }
    }

    .placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .placeholder ha-icon {
      margin-bottom: 16px;
    }

    .placeholder p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
    }

    .area-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
      gap: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .vacation-banner {
      margin-bottom: 20px;
      border-left: 4px solid var(--info-color, #2196f3);
    }

    .presence-banner {
      margin-bottom: 20px;
      border-left: 4px solid var(--info-color, #2196f3);
    }

    .vacation-content {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 12px 16px;
    }

    .vacation-content > ha-icon {
      --mdc-icon-size: 28px;
      color: var(--info-color, #2196f3);
      flex-shrink: 0;
    }

    .vacation-text {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 0;
    }

    .vacation-title {
      font-weight: 500;
      font-size: 14px;
    }

    .vacation-detail {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .stats-bar {
      display: flex;
      align-items: center;
      gap: 24px;
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .stats-actions {
      display: flex;
      align-items: center;
      margin-left: auto;
      gap: 0;
    }

    .hidden-rooms-toggle {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .hidden-rooms-panel {
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .hidden-rooms-header {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .hidden-room-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 0;
    }

    .hidden-room-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .stat-value {
      font-size: 20px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .stat-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .floor-heading {
      font-size: 14px;
      font-weight: 500;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin: 20px 0 8px 0;
    }

    .floor-heading:first-of-type {
      margin-top: 0;
    }

    .reorder-btn {
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .reorder-done {
      font-size: 14px;
      margin-left: auto;
    }
  `,T([h({attribute:!1})],E.prototype,"hass",2),T([h({type:Boolean,reflect:!0})],E.prototype,"narrow",2),T([h({type:Object})],E.prototype,"route",2),T([h({type:Object})],E.prototype,"panel",2),T([m()],E.prototype,"_activeTab",2),T([m()],E.prototype,"_rooms",2),T([m()],E.prototype,"_roomsLoaded",2),T([m()],E.prototype,"_selectedAreaId",2),T([m()],E.prototype,"_analyticsRoom",2),T([m()],E.prototype,"_vacationActive",2),T([m()],E.prototype,"_vacationTemp",2),T([m()],E.prototype,"_vacationUntil",2),T([m()],E.prototype,"_hiddenRooms",2),T([m()],E.prototype,"_showHiddenRooms",2),T([m()],E.prototype,"_controlMode",2),T([m()],E.prototype,"_climateControlActive",2),T([m()],E.prototype,"_presenceEnabled",2),T([m()],E.prototype,"_anyoneHome",2),T([m()],E.prototype,"_presencePersons",2),T([m()],E.prototype,"_presenceAwayAction",2),T([m()],E.prototype,"_saveStatus",2),T([m()],E.prototype,"_roomOrder",2),T([m()],E.prototype,"_groupByFloor",2),T([m()],E.prototype,"_reorderMode",2),T([m()],E.prototype,"_elementsLoaded",2),E=T([R("roommind-panel")],E)})();
